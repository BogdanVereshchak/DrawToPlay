extends CanvasLayer

# Called when the node enters the scene tree for the first time.
func _ready() -> void:
	pass # Replace with function body.


func _process(delta: float) -> void:
	$Control/Panel/Label.text = str(GameStats.score) + " score"
	if GameStats.is_finished:
		$Control/Label.visible = true
