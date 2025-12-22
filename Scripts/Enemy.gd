extends CharacterBody2D

class_name Enemy

@export var speed = 60
@export var gravity = 980

var direction = -1 

func _physics_process(delta: float) -> void:
	if not is_on_floor():
		velocity.y += gravity * delta

	velocity.x = speed * direction

	move_and_slide()

	if is_on_wall():
		flip()
func flip():
	direction *= -1
	
	var sprite = get_node_or_null("Sprite2D") 
	if sprite:
		sprite.flip_h = (direction > 0)

func die():
	queue_free()

func _on_area_2d_body_entered(body: Node) -> void:
	print(body.name)
	if body.name == "Player":
		call_deferred("_reload")

func _reload():
	get_tree().reload_current_scene()
