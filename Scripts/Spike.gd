extends RigidBody2D

func _reload():
	get_tree().reload_current_scene()

func _on_area_2d_body_entered(body: Node2D) -> void:
	if body.name == "Player": 
		call_deferred("_reload")
