.PHONY: help tasks test ayuda tareas

help:
	./tasks --help

tasks:
	./tasks

ayuda: help

tareas: tasks

test:
	python3 -m unittest discover -s tests -v
