extends Node2D

# Шлях до файлу, який згенерував Python
const LEVEL_DATA_PATH = "res://level_data.json" 
# Якщо Python зберігає ззовні проєкту, використовуй user:// або абсолютний шлях

# Бібліотека префабів (перетягни сюди свої сцени в Інспекторі)
@export var platform_scene: PackedScene
@export var spike_scene: PackedScene
@export var enemy_scene: PackedScene
@export var coin_scene: PackedScene
@export var player_scene: PackedScene
@export var finish_scene: PackedScene
@export var box_scene: PackedScene

func _ready():
	load_level()

func load_level():
	# 1. Читаємо файл
	if not FileAccess.file_exists(LEVEL_DATA_PATH):
		print("Файл рівня не знайдено! Запустіть спочатку Python-сканер.")
		return

	var file = FileAccess.open(LEVEL_DATA_PATH, FileAccess.READ)
	var content = file.get_as_text()
	
	# 2. Парсимо JSON
	var json = JSON.new()
	var error = json.parse(content)
	
	if error != OK:
		print("Помилка парсингу JSON")
		return
		
	var data = json.data
	var objects = data["objects"]
	
	# 3. Будуємо світ
	for obj in objects:
		spawn_object(obj)

func spawn_object(obj_data):
	var type = obj_data["type"]
	var x = obj_data["x"]
	var y = obj_data["y"]
	var w = obj_data["width"]
	var h = obj_data["height"]
	
	var instance = null
	
	match type:
		"platform":
			instance = platform_scene.instantiate()
			# Масштабуємо платформу під розмір малюнка
			# Припускаємо, що спрайт платформи має розмір 100x100 пікселів за замовчуванням
			# Тобі треба буде налаштувати скейлінг під свої спрайти
			# instance.scale = Vector2(w / 100.0, h / 100.0) 
			
			# АБО краще використовувати NinePatchRect або змінювати shape колайдера
			_resize_platform_collider(instance, w, h)
			
		"enemy":
			instance = enemy_scene.instantiate()
		"coin":
			instance = coin_scene.instantiate()
		"player_start":
			instance = player_scene.instantiate()
		"finish":
			instance = finish_scene.instantiate()
		"spikes":
			instance = spike_scene.instantiate()
		"box":
			instance = box_scene.instantiate()
			
	if instance:
		instance.position = Vector2(x, y)
		add_child(instance)

# Допоміжна функція для зміни розміру колайдера платформи
func _resize_platform_collider(platform_instance, w, h):
	# Це приклад. У твоїй сцені платформи має бути Sprite2D і CollisionShape2D
	# Змінюємо масштаб ноди, це найпростіший спосіб для прототипу
	# Але краще мати базовий спрайт розміром 1х1 або 32х32 і множити
	var base_size = 64.0 # Припустимо, твій тайл 32px
	platform_instance.scale = Vector2(w / base_size, h / base_size)
