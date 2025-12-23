import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
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

class LevelMakerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Draw-to-Game Scanner")
        self.root.geometry("900x650")
        self.root.configure(bg="#2c3e50")

        self.file_path = None
        self.scan_success = False

        # Стилі
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TButton", padding=10, font=("Helvetica", 12))
        style.configure("TLabel", background="#2c3e50", foreground="white", font=("Helvetica", 10))

        # Ліва панель
        self.left_frame = tk.Frame(root, bg="#34495e", width=250)
        self.left_frame.pack(side="left", fill="y")
        self.left_frame.pack_propagate(False)

        # Логотип/Заголовок
        lbl_title = tk.Label(self.left_frame, text="LEVEL MAKER", font=("Impact", 20), bg="#34495e", fg="#e74c3c")
        lbl_title.pack(pady=20)

        # Кнопка Вибрати фото
        self.btn_select = ttk.Button(self.left_frame, text="📂 1. Обрати фото", command=self.select_image)
        self.btn_select.pack(pady=10, padx=20, fill="x")

        # Кнопка Сканувати
        self.btn_scan = ttk.Button(self.left_frame, text="🧠 2. Аналізувати", command=self.start_scan, state="disabled")
        self.btn_scan.pack(pady=10, padx=20, fill="x")

        # Кнопка Грати
        self.btn_play = ttk.Button(self.left_frame, text="🎮 3. Грати!", command=self.run_game, state="disabled")
        self.btn_play.pack(pady=10, padx=20, fill="x")

        # Інструкція
        lbl_info = tk.Label(self.left_frame, text="Інструкція:\nЧорний - Платформи\nЧервоний - Вороги\nЖовтий - Монети\nЗелений - Старт\nСиній - Фініш", 
                           bg="#34495e", fg="#bdc3c7", justify="left")
        lbl_info.pack(pady=30, padx=20, anchor="w")
        
        # Лог
        self.log_text = tk.Text(self.left_frame, height=10, bg="#2c3e50", fg="#2ecc71", font=("Consolas", 8), relief="flat")
        self.log_text.pack(side="bottom", fill="x", padx=5, pady=5)
        self.log_text.insert("end", "Очікування...\n")

        # Права панель
        self.right_frame = tk.Frame(root, bg="#2c3e50")
        self.right_frame.pack(side="right", fill="both", expand=True)

        self.preview_frame = tk.Frame(self.right_frame, bg="#2c3e50")
        self.preview_frame.pack(expand=True, fill="both")

        self.lbl_image = tk.Label(self.preview_frame, text="Result", bg="#2c3e50", fg="white")
        self.lbl_image.pack(side="left", expand=True, padx=10)

        self.lbl_mask = tk.Label(self.preview_frame, text="Mask", bg="#2c3e50", fg="white")
        self.lbl_mask.pack(side="right", expand=True, padx=10)

    def log(self, message):
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.root.update_idletasks()

    def select_image(self):
        path = filedialog.askopenfilename(filetypes=[("Images", "*.jpg;*.png;*.jpeg")])
        if path:
            self.file_path = path
            self.show_preview(path)
            self.btn_scan.config(state="normal")
            self.btn_play.config(state="disabled")
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
            self.root.after(0, lambda: self.btn_play.config(state="normal"))
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
            self.root.after(0, lambda: messagebox.showinfo("Готово", "Рівень згенеровано! Тисни 'Грати'."))
        else:
            self.root.after(0, lambda: messagebox.showerror("Помилка", "Не вдалося обробити."))

    def run_game(self):
        game_exe = "Game.exe" 
        game_path = os.path.join(os.getcwd(), game_exe)
        
        if os.path.exists(game_path):
            self.log(f"Запуск {game_exe}...")
            subprocess.Popen([game_path])
        else:
            messagebox.showerror("Помилка", f"Не знайдено файл гри: {game_exe}\nПереконайтеся, що він лежить в одній папці з лаунчером.")
            self.log(f"Файл не знайдено: {game_path}")

if __name__ == "__main__":
    root = tk.Tk()
    app = LevelMakerApp(root)
    root.mainloop()