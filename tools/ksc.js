const fs = require("fs");
const path = require("path");
const compiler = require("kaitai-struct-compiler");
const YAML = require("yaml");

async function main([target, schema, outdir]) {
  if (!target || !schema || !outdir) {
    console.error("Usage: node tools/ksc.js <target> <schema.ksy> <outdir>");
    process.exit(2);
  }
  const ksy = YAML.parse(fs.readFileSync(schema, "utf8"));
  const files = await compiler.compile(target, ksy);
  fs.mkdirSync(outdir, { recursive: true });
  for (const [name, content] of Object.entries(files)) {
    fs.writeFileSync(path.join(outdir, name), content, "utf8");
  }
  console.log(`Generated ${Object.keys(files).length} files for '${target}' at '${outdir}'`);
}

main(process.argv.slice(2)).catch(err => { console.error(err); process.exit(1); });
