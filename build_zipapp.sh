
rm -rf build/*

# mkdir build/language_server

# cp -r language_server/* build/language_server


pip install . --target build
echo "from aegis_server.__main__ import main; main()" > build/__main__.py

rm -rf build/numpy*

python -m zipapp build -o ./extension/language_server.pyz