import cv2
import numpy as np
import json
import os

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

def get_smart_color(roi_hsv, mask):
    if cv2.countNonZero(mask) == 0:
        return "neutral"

    mean_val = cv2.mean(roi_hsv, mask=mask)
    h, s, v = mean_val[:3]
    
    if s < 30: return "neutral" 
    
    if h < 10 or h > 120: return "red"
    if 10 <= h < 35: return "yellow"
    if 35 <= h < 85: return "green"
    if 85 <= h < 125: return "blue"
    
    return "unknown"

def scan_level_image(image_path, output_json_path):
    original_img = cv2.imread(image_path)
    if original_img is None:
        print("Помилка: Немає файлу.")
        return

    processing_width = 1080
    scale_factor = processing_width / original_img.shape[1]
    img = resize_image(original_img, width=processing_width)
    
    debug_img = img.copy()

    # Сірий
    gray = np.dot(img[...,::-1], [0.299, 0.587, 0.114]).astype(np.uint8)
    
    # ФІЛЬТРИ
    blurred = cv2.bilateralFilter(gray, 7, 75, 75)

    # БІНАРИЗАЦІЯ
    thresh = cv2.adaptiveThreshold(blurred, 255, 
                                 cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                 cv2.THRESH_BINARY_INV, 11, 2)

    # МОРФОЛОГІЯ
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    
    thresh = cv2.dilate(thresh, kernel, iterations=1)
    

    # Контури
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    level_objects = []
    
    hsv_img = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    print(f"Аналіз: знайдено {len(contours)} контурів.")

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 400: 
            continue
        
        perimeter = cv2.arcLength(cnt, True)
        if perimeter == 0: continue

        # Апроксимація
        epsilon = 0.035 * perimeter
        approx = cv2.approxPolyDP(cnt, epsilon, True)
        vertices = len(approx)

        circularity = 4 * np.pi * (area / (perimeter * perimeter))
        
        x, y, w, h = cv2.boundingRect(approx)
        aspect_ratio = float(w) / h
        
        # Кут нахилу
        rect = cv2.minAreaRect(cnt)
        (_, _), (_, _), angle = rect
        if w < h: angle += 90

        mask = np.zeros(gray.shape, np.uint8)
        cv2.drawContours(mask, [cnt], -1, 255, -1)
        
        # ми беремо перетин маски об'єкта і маски ліній (thresh)
        ink_mask = cv2.bitwise_and(mask, thresh)
        
        color_name = get_smart_color(hsv_img, ink_mask)

        obj_type = "unknown"
        rotation = 0.0

        is_yellow_blob = (color_name == "yellow" and circularity < 0.1)
        is_geometric_circle = (circularity > 0.7)
        
        # Коло
        if (is_geometric_circle or is_yellow_blob) and vertices > 4:
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
                obj_type = "platform"
                rotation = angle
            else:
                if color_name == "blue" and aspect_ratio < 0.6:
                    obj_type = "checkpoint"
                elif color_name == "orange":
                    obj_type = "powerup_box"
                elif color_name == "purple":
                    obj_type = "spring" 
                elif 0.85 <= aspect_ratio <= 1.15:
                    if circularity > 0.6:
                        obj_type = "box"
                    else:
                        obj_type = "spikes"
                else:
                    obj_type = "platform"

        else:
            obj_type = "platform"


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

        cv2.rectangle(debug_img, (x, y), (x+w, y+h), (0, 255, 0), 2)
        cv2.putText(debug_img, f"{obj_type} ({color_name}) v={vertices}, circ={circularity:.2f}", (x, y-5), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)

    final_data = {
        "level_size": {"w": original_img.shape[1], "h": original_img.shape[0]},
        "objects": level_objects
    }
    
    with open(output_json_path, 'w') as f:
        json.dump(final_data, f, indent=4)
    
    print(f"Готово! Знайдено {len(level_objects)} об'єктів.")
    
    cv2.imshow("Smart Scan Result", debug_img)
    cv2.imshow("Mask (Threshold)", thresh)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

if __name__ == "__main__":
    scan_level_image("level_drawing.jpg", "level_data.json")