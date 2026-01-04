from distutils.core import setup

with open("README.md", "r", encoding="utf8") as fh:
    long_description = fh.read()

setup(
    name="degiro_edavki",
    version="1.4.4",
    py_modules=["degiro_edavki", "generators.doh_obr"],
    python_requires=">=3",
    entry_points={
        "console_scripts": ["degiro_edavki=degiro_edavki:main", "degiro-edavki=degiro_edavki:main"]
    },
    author="Primož Sečnik Kolman",
    author_email="primoz@outlook.com",
)
