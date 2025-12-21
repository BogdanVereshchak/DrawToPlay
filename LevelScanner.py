import cv2
import numpy as np
import json
import os

def resize_image(image, width=None, height=None):
    """Розумна зміна розміру зі збереженням пропорцій."""
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

def get_smart_color(roi_hsv, mask):
    """
    Визначає колір, ігноруючи білий фон паперу.
    Ми дивимося тільки на пікселі 'чорнила' (mask).
    """
    if cv2.countNonZero(mask) == 0:
        return "neutral"

    # Середнє значення кольору тільки там, де є лінії (mask)
    mean_val = cv2.mean(roi_hsv, mask=mask)
    h, s, v = mean_val[:3]
    
    # Логіка визначення (трохи розширена для маркерів)
    if s < 30: return "neutral" # Чорний, сірий або білий
    
    if h < 10 or h > 120: return "red"
    if 10 <= h < 25: return "orange"
    if 25 <= h < 35: return "yellow"
    if 35 <= h < 85: return "green"
    if 85 <= h < 125: return "blue"
    
    return "unknown"

def scan_level_image(image_path, output_json_path):
    # 1. Завантаження
    original_img = cv2.imread(image_path)
    if original_img is None:
        print("Помилка: Немає файлу.")
        return

    # Зменшуємо картинку до стандартної ширини (наприклад, 800px)
    # Це критично для універсальності параметрів (epsilon)
    processing_width = 1880
    scale_factor = processing_width / original_img.shape[1]
    img = resize_image(original_img, width=processing_width)
    
    # Копія для малювання результатів
    debug_img = img.copy()

    # 2. Покращена обробка (Preprocessing)
    # Перетворення в сірий
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Розмиття для видалення шуму паперу (Bilateral краще зберігає краї ніж Gaussian)
    blurred = cv2.bilateralFilter(gray, 9, 75, 75)

    # АДАПТИВНИЙ ПОРІГ (Ключ до успіху при поганому світлі)
    # Він розраховує поріг для кожного маленького регіону окремо
    thresh = cv2.adaptiveThreshold(blurred, 255, 
                                 cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                 cv2.THRESH_BINARY_INV, 11, 2)

    # МОРФОЛОГІЯ (Закриваємо дірки в лініях маркера)
    # ВИПРАВЛЕННЯ: Зменшуємо ядро з (5,5) до (3,3), щоб уникнути злипання об'єктів
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    
    # ВИПРАВЛЕННЯ: Робимо dilatation менш агресивним або прибираємо зайвий крок, 
    # щоб платформи не "з'їдали" шипи
    thresh = cv2.dilate(thresh, kernel, iterations=1)

    # 3. Аналіз контурів
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    level_objects = []
    
    # Підготовка HSV картинки для кольору
    hsv_img = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    print(f"Аналіз: знайдено {len(contours)} контурів.")

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 600: # Трохи знизив поріг, щоб бачити маленькі монетки
            continue

        # --- ГЕОМЕТРИЧНИЙ АНАЛІЗ ---
        
        # Периметр
        perimeter = cv2.arcLength(cnt, True)
        if perimeter == 0: continue

        # Апроксимація (спрощення форми)
        epsilon = 0.03 * perimeter
        approx = cv2.approxPolyDP(cnt, epsilon, True)
        vertices = len(approx)

        # Окружність (Circularity): 1.0 = ідеальне коло, < 0.7 = квадрат/трикутник
        circularity = 4 * np.pi * (area / (perimeter * perimeter))
        
        # Обмежувальний прямокутник
        x, y, w, h = cv2.boundingRect(approx)
        aspect_ratio = float(w) / h
        
        # Визначаємо кут нахилу
        rect = cv2.minAreaRect(cnt)
        (_, _), (_, _), angle = rect
        if w < h: angle += 90 # Нормалізація кута

        # --- ВИЗНАЧЕННЯ КОЛЬОРУ ---
        # Створюємо маску саме для цього об'єкта
        mask = np.zeros(gray.shape, np.uint8)
        cv2.drawContours(mask, [cnt], -1, 255, -1)
        
        # Щоб не брати білий папір всередині фігури,
        # ми беремо перетин маски об'єкта і маски ліній (thresh)
        ink_mask = cv2.bitwise_and(mask, thresh)
        
        color_name = get_smart_color(hsv_img, ink_mask)

        # --- ЛОГІКА РОЗПІЗНАВАННЯ ТИПІВ ---
        obj_type = "unknown"
        rotation = 0.0

        # ВИПРАВЛЕННЯ: Більш м'яка перевірка на коло для монет
        # Якщо об'єкт жовтий, ми допускаємо кривішу форму (circularity > 0.5 замість 0.75)
        is_yellow_blob = (color_name == "yellow" and circularity > 0.5)
        is_geometric_circle = (circularity > 0.7)
        
        # 1. Спочатку перевіряємо на коло
        if (is_geometric_circle or is_yellow_blob) and vertices > 4:
            if color_name == "yellow": obj_type = "coin"
            elif color_name == "red": obj_type = "enemy"
            elif color_name == "green": obj_type = "player_start"
            elif color_name == "blue": obj_type = "finish"
            elif color_name == "purple": obj_type = "spring"
            else: obj_type = "rock" # Камінь/декор

        # 2. Трикутники
        elif vertices == 3:
            obj_type = "spikes"

        # 3. Чотирикутники (і схожі на них)
        elif vertices == 4 or vertices == 5: # 5 допускається, якщо один кут трохи зрізаний
            # Перевірка на поворот (нахилена платформа)
            if abs(angle) > 10 and abs(angle) < 80:
                obj_type = "platform"
                rotation = angle
            else:
                # Рівні об'єкти
                if color_name == "blue" and aspect_ratio < 0.6:
                    obj_type = "checkpoint"
                elif color_name == "orange":
                    obj_type = "powerup_box"
                elif color_name == "purple":
                    obj_type = "spring" # Квадратна пружина
                elif 0.85 <= aspect_ratio <= 1.15:
                    if circularity > 0.6:
                        obj_type = "box" # Ящик
                    else:
                        obj_type = "spikes"
                else:
                    obj_type = "platform"

        # 4. Все інше (складні форми)
        else:
            obj_type = "platform"


        # Масштабування координат назад до оригінального розміру
        orig_x = int((x + w/2) / scale_factor)
        orig_y = int((y + h/2) / scale_factor)
        orig_w = int(w / scale_factor)
        orig_h = int(h / scale_factor)

        level_objects.append({
            "type": obj_type,
            "x": orig_x,
            "y": orig_y,
            "width": orig_w,
            "height": orig_h,
            "rotation": float(rotation),
            "debug_info": f"{color_name}, v={vertices}, circ={circularity:.2f}"
        })

        # Візуалізація
        cv2.rectangle(debug_img, (x, y), (x+w, y+h), (0, 255, 0), 2)
        cv2.putText(debug_img, f"{obj_type} ({color_name}) v={vertices}, circ={circularity:.2f}", (x, y-5), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)

    # Збереження
    final_data = {
        "level_size": {"w": original_img.shape[1], "h": original_img.shape[0]},
        "objects": level_objects
    }
    
    with open(output_json_path, 'w') as f:
        json.dump(final_data, f, indent=4)
    
    print(f"Готово! Знайдено {len(level_objects)} об'єктів.")
    
    # Показати результат (зменшений)
    cv2.imshow("Smart Scan Result", debug_img)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

if __name__ == "__main__":
    scan_level_image("level_drawing.jpg", "level_data.json")