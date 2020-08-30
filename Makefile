flake8:
	flake8 miso

test_lib:
	BRANCH=$(ENABLE_BRANCH_COVERAGE) py.test test --strict --timeout 30 --cov --cov-config=$(CURDIR)/.coveragerc

