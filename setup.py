from setuptools import setup

setup(
    name="flip-disc",
    version="0.0.1",
    description="To display various outputs on AphaZeta flip dot display",
    author="Garrett Johnson",
    # packages=find_packages(include=["flip_disc"]),
    install_requires=[
        "aioserial==1.3.0",
        "cycler==0.11.0",
        "fonttools==4.33.3",
        "kiwisolver==1.4.3",
        "matplotlib==3.5.2",
        "numpy==1.23.0",
        "opencv-python==4.6.0.66",
        "opensimplex==0.4.3",
        "packaging==21.3",
        "Pillow==9.2.0",
        "pyparsing==3.0.9",
        "pyserial==3.5",
        "python-dateutil==2.8.2",
        "scikit-video==1.1.11",
        "scipy==1.8.1",
        "six==1.16.0",
    ],
    setup_requires=['pytest-runner', 'flake8'],
    tests_require=['pytest'],
)