flake8:
	flake8 miso

image:
	docker build . -t miso:dev

test_lib:
	BRANCH=$(ENABLE_BRANCH_COVERAGE) py.test test --strict --timeout 30 --cov --cov-config=$(CURDIR)/.coveragerc

