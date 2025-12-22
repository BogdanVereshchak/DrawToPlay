extends Node

var coins_collected : int = 0
var is_finished:bool = false

var score : int :
	set(v):
		v  = coins_collected * 100
	get():
		return coins_collected * 100
