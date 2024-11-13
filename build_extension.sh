
rm -rf build/*

mkdir build
mkdir build/language_server

cp -r language_server/* build/language_server

echo "from language_server.__main__ import main; main()" > build/__main__.py

pip install ../mecha ../bolt --target build

rm -rf build/numpy*

python -m zipapp build -o ./extension/language_server.pyz