extends Area2D


func _on_body_entered(_body: Node2D) -> void:
	GameStats.coins_collected += 1
	print(GameStats.coins_collected)
	queue_free()
