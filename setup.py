import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="miso",
    version="0.0.2",
    author="Alex Wilson",
    author_email="admin@c3group.com.au",
    description="A collection of extensions and helpers for developing Nameko microservices",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="",
    packages=setuptools.find_packages(),
    classifiers=(
        "Programming Language :: Python :: 3",
	"Software Development :: Libraries :: Python Modules"
    ),
)

