.PHONY: test lint sim eval

test:
	python -m pytest tests/ -v

lint:
	python -m py_compile src/ct/*.py src/ct/*/*.py

sim:
	python -m ct.sim.engine

eval:
	python -m ct.eval.harness
