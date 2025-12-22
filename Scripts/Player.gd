extends CharacterBody2D

@export var speed = 300.0
@export var jump_velocity = -400.0
@export var dash_speed = 1000.0
@export var dash_duration = 0.2
@export var dash_cooldown = 0.8

var gravity = ProjectSettings.get_setting("physics/2d/default_gravity")
var is_dashing = false
var can_dash = true

func _physics_process(delta):
	if is_dashing:
		move_and_slide()
		return

	if not is_on_floor():
		velocity.y += gravity * delta

	if Input.is_action_just_pressed("jump") and is_on_floor():
		velocity.y = jump_velocity

	var direction = Input.get_axis("left", "right")
	
	if direction:
		velocity.x = direction * speed
	else:
		velocity.x = move_toward(velocity.x, 0, speed)

	if Input.is_action_just_pressed("dash") and can_dash and direction != 0:
		start_dash(direction)

	move_and_slide()

func start_dash(direction):
	is_dashing = true
	can_dash = false
	
	velocity = Vector2(direction * dash_speed, 0)
	
	await get_tree().create_timer(dash_duration).timeout
	is_dashing = false
	velocity.x = move_toward(velocity.x, 0, speed)
	
	await get_tree().create_timer(dash_cooldown).timeout
	can_dash = true
