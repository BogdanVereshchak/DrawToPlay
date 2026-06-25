import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk, ImageDraw, ImageFilter
import cv2
import numpy as np
import json
import os
import subprocess
import threading

def resize_image(image, width=None, height=None):
    dim = None
    (h, w) = image.shape[:2]

    if width is None and height is None:
        return image

    if width is None:
        r = height / float(h)
        dim = (int(w * r), height)
    else:
        r = width / float(w)
        dim = (width, int(h * r))

    return cv2.resize(image, dim, interpolation=cv2.INTER_AREA)

def get_color_mask(hsv_img, color_name):
    s_min = 40
    v_min = 40
    if color_name == "red":
        mask1 = cv2.inRange(hsv_img, (0, s_min, v_min), (10, 255, 255))
        mask2 = cv2.inRange(hsv_img, (130, s_min, v_min), (180, 255, 255))
        return mask1 | mask2
    elif color_name == "yellow": return cv2.inRange(hsv_img, (10, s_min, v_min), (35, 255, 255))
    elif color_name == "green": return cv2.inRange(hsv_img, (35, s_min, v_min), (85, 255, 255))
    elif color_name == "blue": return cv2.inRange(hsv_img, (85, s_min, v_min), (125, 255, 255))
    return np.zeros(hsv_img.shape[:2], dtype=np.uint8)

def analyze_scan(image_path, output_json_path, log_callback=None):
    if log_callback: log_callback(f"Завантаження: {image_path}")
    
    original_img = cv2.imread(image_path)
    if original_img is None:
        if log_callback: log_callback("Помилка: Невірний файл зображення.")
        return False, None

    processing_width = 1000
    scale_factor = processing_width / original_img.shape[1]
    img = resize_image(original_img, width=processing_width)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.bilateralFilter(gray, 7, 75, 75)
    all_ink_mask = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2)
    kernel_small = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    all_ink_mask = cv2.morphologyEx(all_ink_mask, cv2.MORPH_CLOSE, kernel_small)
    debug_mask = all_ink_mask.copy()

    level_objects = []
    colors_to_check = ["red", "yellow", "green", "blue"]

    count_found = 0
    for color in colors_to_check:
        color_pixels = get_color_mask(hsv, color)
        object_mask = cv2.bitwise_and(all_ink_mask, all_ink_mask, mask=color_pixels)
        object_mask = cv2.dilate(object_mask, kernel_small, iterations=1)
        
        contours, _ = cv2.findContours(object_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        debug_mask = cv2.bitwise_or(debug_mask, object_mask)
        
        for cnt in contours:
            obj_data = process_contour(cnt, color, scale_factor)
            if obj_data:
                level_objects.append(obj_data)
                count_found += 1

                x, y, w, h = obj_data["debug_rect"]
                cv2.rectangle(all_ink_mask, (x-2, y-2), (x+w+2, y+h+2), 0, -1)

    all_ink_mask = cv2.morphologyEx(all_ink_mask, cv2.MORPH_CLOSE, kernel_small)
    contours_struct, _ = cv2.findContours(all_ink_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    for cnt in contours_struct:
        obj_data = process_contour(cnt, "neutral", scale_factor)
        if obj_data:
            if obj_data["width"] < 15 or obj_data["height"] < 15: continue
            level_objects.append(obj_data)
            count_found += 1

    # Збереження
    final_data = {
        "level_size": {"w": original_img.shape[1], "h": original_img.shape[0]},
        "objects": level_objects
    }
    
    with open(output_json_path, 'w') as f:
        json.dump(final_data, f, indent=4)
        
    if log_callback: log_callback(f"Успіх! Знайдено {count_found} об'єктів.")
    
    for obj in level_objects:
        x, y, w, h = obj["debug_rect"]
        label = f'{obj["type"]} | {obj["debug_info"]}'
        
        cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)
        
        cv2.putText(img, obj["type"], (x, y - 18),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)

        cv2.putText(img, obj["debug_info"], (x, y - 4),
            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

    return True, img, debug_mask

def process_contour(cnt, color_name, scale_factor):
    area = cv2.contourArea(cnt)
    if area < 300: return None
    perimeter = cv2.arcLength(cnt, True)
    if perimeter == 0: return None

    epsilon = 0.03 * perimeter
    approx = cv2.approxPolyDP(cnt, epsilon, True)
    vertices = len(approx)
    circularity = 4 * np.pi * (area / (perimeter * perimeter))
    
    x, y, w, h = cv2.boundingRect(approx)
    aspect_ratio = float(w) / h
    rect = cv2.minAreaRect(cnt)
    (_, _), (_, _), angle = rect
    if w < h: angle += 90

    obj_type = "platform" # Default
    rotation = 0.0

    is_circle = (circularity > 0.7) or (color_name == "yellow" and circularity < 0.1)

    if is_circle and vertices > 4:
        if color_name == "yellow": obj_type = "coin"
        elif color_name == "red": obj_type = "enemy"
        elif color_name == "green": obj_type = "player_start"
        elif color_name == "blue": obj_type = "finish"
        elif color_name == "purple": obj_type = "spring"
        else: obj_type = "rock"

    elif vertices == 3:
        obj_type = "spikes"

    elif vertices == 4 or vertices == 5:
        if abs(angle) > 10 and abs(angle) < 80:
            rotation = angle
        else:
            if color_name == "blue" and aspect_ratio < 0.6: obj_type = "checkpoint"
            elif color_name == "orange": obj_type = "powerup_box"
            elif color_name == "purple": obj_type = "spring"
            elif 0.85 <= aspect_ratio <= 1.15:
                if circularity > 0.6: obj_type = "box"
                else: obj_type = "spikes"
            else: obj_type = "platform"

    orig_x = int((x + w/2) / scale_factor)
    orig_y = int((y + h/2) / scale_factor)
    orig_w = int(w / scale_factor)
    orig_h = int(h / scale_factor)
    
    return {
        "type": obj_type,
        "x": orig_x, "y": orig_y,
        "width": orig_w, "height": orig_h,
        "rotation": float(rotation),
        "debug_rect": (x, y, w, h),
        "debug_info": f"{color_name}, v={vertices}, circ={circularity:.2f}"
    }

class ModernButton(tk.Canvas):
    """Custom modern button with gradient and hover effects"""
    def __init__(self, parent, text, command, bg_color="#3498db", hover_color="#2980b9", 
                 text_color="white", width=200, height=50, icon="", state="normal"):
        super().__init__(parent, width=width, height=height, bg=parent['bg'], 
                        highlightthickness=0, cursor="hand2" if state == "normal" else "arrow")
        
        self.command = command
        self.bg_color = bg_color
        self.hover_color = hover_color
        self.text_color = text_color
        self.text = text
        self.icon = icon
        self.width = width
        self.height = height
        self.is_hovered = False
        self.state = state
        
        self.draw_button()
        
        if state == "normal":
            self.bind("<Enter>", self.on_enter)
            self.bind("<Leave>", self.on_leave)
            self.bind("<Button-1>", self.on_click)
    
    def draw_button(self):
        self.delete("all")
        
        # Determine color based on state
        if self.state == "disabled":
            color = "#7f8c8d"
        elif self.is_hovered:
            color = self.hover_color
        else:
            color = self.bg_color
        
        # Draw rounded rectangle with shadow
        radius = 10
        shadow_offset = 3
        
        # Shadow
        if self.state == "normal":
            self.create_rounded_rect(shadow_offset, shadow_offset, 
                                    self.width, self.height, 
                                    radius, fill="#1a1a1a", outline="")
        
        # Main button
        self.create_rounded_rect(0, 0, self.width - shadow_offset, 
                                self.height - shadow_offset, 
                                radius, fill=color, outline="")
        
        # Text
        full_text = f"{self.icon} {self.text}" if self.icon else self.text
        text_color = "#bdc3c7" if self.state == "disabled" else self.text_color
        self.create_text(self.width // 2, self.height // 2, 
                        text=full_text, fill=text_color, 
                        font=("Segoe UI", 11, "bold"))
    
    def create_rounded_rect(self, x1, y1, x2, y2, radius, **kwargs):
        points = [
            x1 + radius, y1,
            x2 - radius, y1,
            x2, y1,
            x2, y1 + radius,
            x2, y2 - radius,
            x2, y2,
            x2 - radius, y2,
            x1 + radius, y2,
            x1, y2,
            x1, y2 - radius,
            x1, y1 + radius,
            x1, y1
        ]
        return self.create_polygon(points, smooth=True, **kwargs)
    
    def on_enter(self, event):
        if self.state == "normal":
            self.is_hovered = True
            self.draw_button()
    
    def on_leave(self, event):
        self.is_hovered = False
        self.draw_button()
    
    def on_click(self, event):
        if self.state == "normal" and self.command:
            self.command()
    
    def config_state(self, state):
        self.state = state
        self.config(cursor="hand2" if state == "normal" else "arrow")
        if state == "normal":
            self.bind("<Enter>", self.on_enter)
            self.bind("<Leave>", self.on_leave)
            self.bind("<Button-1>", self.on_click)
        else:
            self.unbind("<Enter>")
            self.unbind("<Leave>")
            self.unbind("<Button-1>")
        self.draw_button()

class LevelMakerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Draw-to-Game Scanner")
        self.root.geometry("1100x700")
        
        # Modern gradient background
        self.root.configure(bg="#1a1a2e")

        self.file_path = None
        self.scan_success = False

        # Create main container with gradient effect
        self.main_container = tk.Frame(root, bg="#1a1a2e")
        self.main_container.pack(fill="both", expand=True, padx=10, pady=10)

        # Ліва панель з градієнтом
        self.left_frame = tk.Frame(self.main_container, bg="#16213e", width=280)
        self.left_frame.pack(side="left", fill="y", padx=(0, 10))
        self.left_frame.pack_propagate(False)

        # Add decorative top bar
        top_bar = tk.Frame(self.left_frame, bg="#0f3460", height=5)
        top_bar.pack(fill="x")

        # Логотип/Заголовок з тінню
        title_frame = tk.Frame(self.left_frame, bg="#16213e")
        title_frame.pack(pady=25)
        
        lbl_title = tk.Label(title_frame, text="🎮 LEVEL MAKER", 
                            font=("Segoe UI", 24, "bold"), 
                            bg="#16213e", fg="#e94560")
        lbl_title.pack()
        
        lbl_subtitle = tk.Label(title_frame, text="Draw • Scan • Play", 
                               font=("Segoe UI", 10, "italic"), 
                               bg="#16213e", fg="#a8dadc")
        lbl_subtitle.pack()

        # Separator line
        separator1 = tk.Frame(self.left_frame, bg="#0f3460", height=2)
        separator1.pack(fill="x", padx=20, pady=15)

        # Buttons container
        btn_container = tk.Frame(self.left_frame, bg="#16213e")
        btn_container.pack(pady=10, padx=20, fill="x")

        # Custom styled buttons
        self.btn_select = ModernButton(btn_container, "Обрати фото", 
                                       self.select_image, 
                                       bg_color="#3498db", 
                                       hover_color="#2980b9",
                                       icon="📂", width=240, height=55)
        self.btn_select.pack(pady=8)

        self.btn_scan = ModernButton(btn_container, "Аналізувати", 
                                     self.start_scan, 
                                     bg_color="#2ecc71", 
                                     hover_color="#27ae60",
                                     icon="🧠", width=240, height=55, state="disabled")
        self.btn_scan.pack(pady=8)

        self.btn_play = ModernButton(btn_container, "Грати!", 
                                     self.run_game, 
                                     bg_color="#e74c3c", 
                                     hover_color="#c0392b",
                                     icon="🎮", width=240, height=55, state="disabled")
        self.btn_play.pack(pady=8)

        # Separator line
        separator2 = tk.Frame(self.left_frame, bg="#0f3460", height=2)
        separator2.pack(fill="x", padx=20, pady=15)

        # Інструкція з іконками
        info_frame = tk.Frame(self.left_frame, bg="#16213e")
        info_frame.pack(pady=10, padx=20, fill="x")
        
        lbl_info_title = tk.Label(info_frame, text="📋 Інструкція:", 
                                 font=("Segoe UI", 11, "bold"), 
                                 bg="#16213e", fg="#f1f1f1")
        lbl_info_title.pack(anchor="w", pady=(0, 10))
        
        instructions = [
            ("⬛", "Чорний", "Платформи"),
            ("🔴", "Червоний", "Вороги"),
            ("🟡", "Жовтий", "Монети"),
            ("🟢", "Зелений", "Старт"),
            ("🔵", "Синій", "Фініш"),
            ("🔺", "Трикутник", "Шипи")
        ]
        
        for icon, color, desc in instructions:
            item_frame = tk.Frame(info_frame, bg="#16213e")
            item_frame.pack(anchor="w", pady=2)
            
            tk.Label(item_frame, text=icon, bg="#16213e", fg="white", 
                    font=("Segoe UI", 10)).pack(side="left", padx=(0, 5))
            tk.Label(item_frame, text=f"{color}:", bg="#16213e", 
                    fg="#a8dadc", font=("Segoe UI", 9, "bold")).pack(side="left")
            tk.Label(item_frame, text=desc, bg="#16213e", 
                    fg="#bdc3c7", font=("Segoe UI", 9)).pack(side="left", padx=(5, 0))
        
        # Лог з рамкою
        log_frame = tk.Frame(self.left_frame, bg="#0f3460")
        log_frame.pack(side="bottom", fill="x", padx=10, pady=10)
        
        log_title = tk.Label(log_frame, text="📊 Лог подій", 
                            font=("Segoe UI", 9, "bold"), 
                            bg="#0f3460", fg="#a8dadc")
        log_title.pack(anchor="w", padx=5, pady=(5, 2))
        
        self.log_text = tk.Text(log_frame, height=8, bg="#0d1b2a", 
                               fg="#2ecc71", font=("Consolas", 9), 
                               relief="flat", padx=10, pady=5,
                               insertbackground="#2ecc71")
        self.log_text.pack(fill="x", padx=5, pady=(0, 5))
        self.log_text.insert("end", "✓ Система готова до роботи...\n")

        # Права панель з рамками
        self.right_frame = tk.Frame(self.main_container, bg="#1a1a2e")
        self.right_frame.pack(side="right", fill="both", expand=True)

        # Title for preview area
        preview_title = tk.Label(self.right_frame, text="🖼️ Попередній перегляд", 
                                font=("Segoe UI", 14, "bold"), 
                                bg="#1a1a2e", fg="#f1f1f1")
        preview_title.pack(pady=(0, 10))

        self.preview_frame = tk.Frame(self.right_frame, bg="#1a1a2e")
        self.preview_frame.pack(expand=True, fill="both")

        # Result preview with border
        result_container = tk.Frame(self.preview_frame, bg="#0f3460", padx=2, pady=2)
        result_container.pack(side="left", expand=True, fill="both", padx=5)
        
        result_label = tk.Label(result_container, text="Результат", 
                               font=("Segoe UI", 10, "bold"), 
                               bg="#0f3460", fg="#a8dadc")
        result_label.pack(pady=5)
        
        self.lbl_image = tk.Label(result_container, text="Оберіть зображення\nдля початку роботи", 
                                 bg="#0d1b2a", fg="#7f8c8d",
                                 font=("Segoe UI", 12), 
                                 width=40, height=20)
        self.lbl_image.pack(expand=True, fill="both", padx=5, pady=(0, 5))

        # Mask preview with border
        mask_container = tk.Frame(self.preview_frame, bg="#0f3460", padx=2, pady=2)
        mask_container.pack(side="right", expand=True, fill="both", padx=5)
        
        mask_label = tk.Label(mask_container, text="Маска", 
                             font=("Segoe UI", 10, "bold"), 
                             bg="#0f3460", fg="#a8dadc")
        mask_label.pack(pady=5)
        
        self.lbl_mask = tk.Label(mask_container, text="Маска з'явиться\nпісля аналізу", 
                                bg="#0d1b2a", fg="#7f8c8d",
                                font=("Segoe UI", 12), 
                                width=40, height=20)
        self.lbl_mask.pack(expand=True, fill="both", padx=5, pady=(0, 5))

    def log(self, message):
        self.log_text.insert("end", f"• {message}\n")
        self.log_text.see("end")
        self.root.update_idletasks()

    def select_image(self):
        path = filedialog.askopenfilename(filetypes=[("Images", "*.jpg;*.png;*.jpeg")])
        if path:
            self.file_path = path
            self.show_preview(path)
            self.btn_scan.config_state("normal")
            self.btn_play.config_state("disabled")
            self.log(f"Обрано: {os.path.basename(path)}")

    def show_preview(self, path):
        img = Image.open(path)
        img.thumbnail((600, 500)) 
        self.tk_img = ImageTk.PhotoImage(img)
        self.lbl_image.config(image=self.tk_img, text="")

    def start_scan(self):
        if not self.file_path: return
        self.log("Початок аналізу...")
        
        threading.Thread(target=self._scan_process).start()

    def _scan_process(self):
        json_path = os.path.join(os.getcwd(), "level_data.json")
        
        success, processed_img_cv, mask_cv = analyze_scan(self.file_path, json_path, self.log)
        
        if success:
            self.scan_success = True
            self.root.after(0, lambda: self.btn_play.config_state("normal"))
            rgb_img = cv2.cvtColor(processed_img_cv, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb_img)
            pil_img.thumbnail((600, 500))
            self.tk_img_processed = ImageTk.PhotoImage(pil_img)
            self.root.after(0, lambda: self.lbl_image.config(image=self.tk_img_processed))
            mask_rgb = cv2.cvtColor(mask_cv, cv2.COLOR_GRAY2RGB)
            mask_pil = Image.fromarray(mask_rgb)
            mask_pil.thumbnail((600, 500))

            self.tk_img_mask = ImageTk.PhotoImage(mask_pil)
            self.root.after(0, lambda: self.lbl_mask.config(image=self.tk_img_mask))
            self.root.after(0, lambda: messagebox.showinfo("✓ Готово", "Рівень успішно згенеровано!\n\nТисни 'Грати' для запуску гри."))
        else:
            self.root.after(0, lambda: messagebox.showerror("✗ Помилка", "Не вдалося обробити зображення.\n\nПеревірте формат файлу."))

    def run_game(self):
        game_exe = "Game.exe" 
        game_path = os.path.join(os.getcwd(), game_exe)
        
        if os.path.exists(game_path):
            self.log(f"Запуск {game_exe}...")
            subprocess.Popen([game_path])
        else:
            messagebox.showerror("✗ Помилка", f"Не знайдено файл гри: {game_exe}\n\nПереконайтеся, що він лежить в одній папці з лаунчером.")
            self.log(f"Файл не знайдено: {game_path}")

if __name__ == "__main__":
    root = tk.Tk()
    app = LevelMakerApp(root)
    root.mainloop()
