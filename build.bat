poetry run shiv --preamble preamble.py -e language_server:__main__:main -o ./extension/language_server.pyz .
cd ./extension && npm run package