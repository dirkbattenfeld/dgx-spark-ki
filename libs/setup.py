from setuptools import setup, find_packages

setup(
    name="my_libs",
    version="0.1.0",
    # find_packages() findet automatisch alle Unterordner mit __init__.py
    packages=find_packages(),
    install_requires=[
        "httpx",
        "PyYAML",
        "pydantic",
        "fsspec",
        "s3fs",
        "python-dotenv"
    ],
)
