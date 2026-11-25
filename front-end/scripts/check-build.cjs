const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

const root = path.resolve(__dirname, '..');
const errors = [];

function walk(dir, ext) {
  const results = [];
  if (!fs.existsSync(dir)) return results;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) results.push(...walk(full, ext));
    else if (entry.name.endsWith(ext)) results.push(full);
  }
  return results;
}

const jsFiles = [path.join(root, 'serve.cjs'), ...walk(path.join(root, 'src', 'js'), '.js')];
for (const file of jsFiles) {
  try {
    execFileSync(process.execPath, ['--check', file], { stdio: 'pipe' });
  } catch (err) {
    errors.push(`JS syntax error in ${path.relative(root, file)}: ${err.stderr?.toString() || err.message}`);
  }
}

const cssFiles = walk(path.join(root, 'src', 'css'), '.css');
for (const file of cssFiles) {
  const text = fs.readFileSync(file, 'utf8');
  let depth = 0;
  for (let i = 0; i < text.length; i++) {
    if (text[i] === '{') depth++;
    else if (text[i] === '}') depth--;
    if (depth < 0) {
      errors.push(`CSS unmatched '}' in ${path.relative(root, file)}`);
      break;
    }
  }
  if (depth !== 0) {
    errors.push(`CSS unclosed '{' (depth=${depth}) in ${path.relative(root, file)}`);
  }
}

const indexPath = path.join(root, 'index.html');
if (!fs.existsSync(indexPath)) {
  errors.push('Missing index.html');
} else {
  const html = fs.readFileSync(indexPath, 'utf8');
  const assetRefs = [...html.matchAll(/<(?:link[^>]+href|script[^>]+src)=["']([^"']+)["']/gi)].map(m => m[1]);
  for (const ref of assetRefs) {
    if (/^(https?:|data:|\/\/)/i.test(ref)) continue;
    const cleanRef = ref.split('?')[0].split('#')[0];
    const target = path.resolve(root, cleanRef);
    if (!fs.existsSync(target)) {
      errors.push(`Missing asset referenced in index.html: ${ref}`);
    }
  }
}

if (errors.length) {
  console.error('BUILD CHECK FAILED:');
  for (const err of errors) console.error(' - ' + err);
  process.exit(1);
}

console.log(`BUILD CHECK PASSED: ${jsFiles.length} JS files, ${cssFiles.length} CSS files, index.html assets verified.`);
