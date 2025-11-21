import os
import sys
from lbry import __name__, __version__
from setuptools import setup, find_packages

BASE = os.path.dirname(__file__)
with open(os.path.join(BASE, 'README.md'), encoding='utf-8') as fh:
    long_description = fh.read()

setup(
    name=__name__,
    version=__version__,
    author="LBRY Inc.",
    author_email="hello@lbry.com",
    url="https://lbry.com",
    description="A decentralized media library and marketplace",
    long_description=long_description,
    long_description_content_type="text/markdown",
    keywords="lbry protocol media",
    license='MIT',
    python_requires='>=3.14',
    packages=find_packages(exclude=('tests',)),
    zip_safe=False,
    entry_points={
        'console_scripts': [
            'lbrynet=lbry.extras.cli:main',
            'orchstr8=lbry.wallet.orchstr8.cli:main'
        ],
    },
    install_requires=[
        'aiohttp>=3.10.0',
        # aiosignal is now a dependency of aiohttp, no need to specify separately
        'aioupnp==0.0.18',
        'appdirs==1.4.3',
        'certifi>=2023.11.17',
        'colorama>=0.4.6',
        'distro==1.9.0',
        'base58==1.0.0',
        # Modern cffi with full Python 3.14 support
        'cffi>=1.17.0',
        'cryptography>=42.0.0',
        'protobuf==3.20.3',
        'prometheus_client==0.20.0',
        'ecdsa==0.19.0',
        'pyyaml>=6.0.1',
        'docopt==0.6.2',
        'hachoir==3.3.0',
        'coincurve==20.0.0',
        'pbkdf2==1.3',
        'filetype==1.2.0',
        # setuptools provides pkg_resources, needed for version comparison
        'setuptools>=70.0.0',
    ],
    extras_require={
        'lint': [
            'pylint>=3.0.0'
        ],
        'test': [
            'coverage',
            'jsonschema==4.4.0',
        ],
        'hub': [
            'hub@git+https://github.com/lbryio/hub.git@929448d64bcbe6c5e476757ec78456beaa85e56a'
        ],
        'torrent': [
            'libtorrent>=2.0.6,<2.0.12'
        ]
    },
    classifiers=[
        'Framework :: AsyncIO',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Operating System :: OS Independent',
        'Topic :: Internet',
        'Topic :: Software Development :: Testing',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: System :: Distributed Computing',
        'Topic :: Utilities',
    ],
)
