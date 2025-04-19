from setuptools import setup, find_packages

setup(
    name="django-async-manager",
    version="0.1.0",
    description="A professional Django library for managing asynchronous tasks with advanced scheduling and dependency management.",
    author="Michał Konwiak",
    author_email="michalkonwiak1@gmail.com",
    url="https://github.com/michalkonwiak/django-async-manager",
    packages=find_packages(exclude=["tests*"]),
    include_package_data=True,
    install_requires=[
        "Django>=3.2",
        "croniter>=6.0.0",
        "setuptools>=78.1.0",
    ],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Web Environment",
        "Framework :: Django",
        "Framework :: Django :: 4.2",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.12",
)
