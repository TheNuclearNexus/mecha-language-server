const JsZip = require("jszip");
const fs = require("fs");

const packagesToRemove = [
    "numpy",
    "pip",
    "setuptools",
    "pydantic",
    "_pytest",
    "jinja2"
];

async function main() {
    const zip = await JsZip.loadAsync(fs.readFileSync("language_server.pyz"));

    const paths = [];
    zip.forEach((path, file) => {
        for (const package of packagesToRemove) {
            if (path.startsWith(package)) {
                paths.push(path);
                return;
            }
        }
        if (path.includes("__pycache__"))
            paths.push(path)
    });

    for (const path of paths) {
        console.log("removed", path);
        zip.remove(path);
    }

    fs.writeFileSync(
        "language_server.pyz",
        await zip.generateAsync({ type: "nodebuffer" })
    );
}

main();
