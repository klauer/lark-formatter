from setuptools import setup

with open("requirements.txt", "rt") as fp:
    install_requires = [
        line for line in fp.read().splitlines()
        if line and not line.startswith("#")
    ]

setup(
    name="lark-formatter",
    license="BSD",
    author="SLAC National Accelerator Laboratory",
    py_modules=["lark_formatter"],
    description="Tool to reformat lark-parser grammars",
    entry_points={
        "console_scripts": ["lark-format = lark_formatter:main"],
    },
    install_requires=install_requires,
    python_requires=">=3.7",
)
