import os
import setuptools


with open(os.path.join(os.path.dirname(__file__), "README.md"), "r") as readme:
    long_description = readme.read()

setuptools.setup(
    name="twitterhal",
    version="0.0.1",
    author="Robert Huselius",
    author_email="robert@huseli.us",
    description="A MegaHAL bot for Twitter",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Eboreg/twitterhal",
    packages=["twitterhal"],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: OS Independent",
        "Development Status :: 1 - Planning",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "Topic :: Communications",
        "Topic :: Internet",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Text Processing :: Linguistic",
    ],
    python_requires=">=3.6",
    install_requires=[
        "megahal>=0.3",
        "python-Levenshtein",
        "python-twitter",
        "emoji",
        "detectlanguage",
    ],
    dependency_links=[
        "https://github.com/Eboreg/megahal/tarball/master#egg=megahal-0.3",
    ],
)
