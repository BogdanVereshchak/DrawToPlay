@tool
extends Node2D

const LEVEL_DATA_PATH = "res://level_data.json"

@export var platform_scene: PackedScene
@export var spike_scene: PackedScene
@export var enemy_scene: PackedScene
@export var coin_scene: PackedScene
@export var player_scene: PackedScene
@export var finish_scene: PackedScene
@export var box_scene: PackedScene

# Посилання на контейнери
@onready var containers = {
	"platform": $Platforms,
	"spikes": $Spikes,
	"enemy": $Enemies,
	"coin": $Coins,
	"player_start": $PlayerStart,
	"finish": $Finish,
	"box": $Boxes
}

func _ready():
	load_level()

func load_level():
	if not FileAccess.file_exists(LEVEL_DATA_PATH):
		print("Помилка: Файл рівня не знайдено.")
		return

	var file = FileAccess.open(LEVEL_DATA_PATH, FileAccess.READ)
	var json = JSON.new()
	var error = json.parse(file.get_as_text())
	
	if error != OK:
		print("Помилка парсингу JSON")
		return
		
	var data = json.data
	
	_clear_level()
	
	for obj in data["objects"]:
		spawn_object(obj)

func _clear_level():
	for container in containers.values():
		for child in container.get_children():
			child.queue_free()

func spawn_object(obj_data):
	var type = obj_data["type"]
	var x = obj_data["x"]
	var y = obj_data["y"]
	var w = obj_data["width"]
	var h = obj_data["height"]
	var rot = obj_data.get("rotation", 0.0)
	
	var instance = null
	
	match type:
		"platform":
			instance = platform_scene.instantiate()
			_resize_platform_collider(instance, w, h)
		"enemy": instance = enemy_scene.instantiate()
		"coin": instance = coin_scene.instantiate()
		"player_start": instance = player_scene.instantiate()
		"finish": instance = finish_scene.instantiate()
		"spikes": instance = spike_scene.instantiate()
		"box": instance = box_scene.instantiate()
		
	if instance:
		instance.position = Vector2(x, y)
		instance.rotation_degrees = rot
		
		if containers.has(type):
			containers[type].add_child(instance)
		else:
			add_child(instance)

func _resize_platform_collider(platform_instance, w, h):
	var base_size = 64.0 
	platform_instance.scale = Vector2(w / base_size, h / base_size)
