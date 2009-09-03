from setuptools import setup, find_packages
setup(
    name = 'Porigon Z',
    version = '0.0',
    description = 'DS game image inspector',
    author = 'Eevee',
    author_email = 'git@veekun.com',
    url = 'http://git.veekun.com',

    packages = find_packages(),
    package_data = { '': ['data'] },
    install_requires = ['construct>=2.0'],
    entry_points = {
        'console_scripts': [
            'porigon-z = porigonz:main',
        ],
    },
)

