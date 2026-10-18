.PHONY: run test smoke zip
run:
	./run.sh --install
test:
	python scripts/run_evals.py
smoke:
	python scripts/smoke_test.py
zip:
	python scripts/make_zip.py
