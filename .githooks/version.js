// La versión del repositorio, que sube sola con cada commit según su prefijo.
//
//   feat: algo nuevo (skill, script, área)      → sube el MENOR   1.4.2 → 1.5.0
//   fix:  ajuste a algo que ya existe           → sube el PARCHE  1.4.2 → 1.4.3
//   chore: datos puros                          → no sube
//   feat!: o fix!: cambia cómo se usa el repo   → sube el MAYOR   1.4.2 → 2.0.0
//
// La llaman dos hooks: `commit-msg` rechaza un mensaje sin prefijo, y `post-commit`
// sube VERSION, añade la entrada al CHANGELOG, las mete en el mismo commit con un
// --amend y pone la etiqueta. Ver tickets/abiertos/versionar-todos-los-repos.md.

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const PREFIJO = /^(feat|fix|chore)(\([^)]+\))?(!)?: \S/;
const LIBRES = /^(Merge|Revert|fixup!|squash!)/;

const git = (...a) => execFileSync('git', a, { encoding: 'utf8' }).trim();
const raiz = git('rev-parse', '--show-toplevel');
const gitDir = git('rev-parse', '--absolute-git-dir');

function commitMsg(fichero) {
  const linea = fs.readFileSync(fichero, 'utf8').split('\n')[0];
  if (PREFIJO.test(linea) || LIBRES.test(linea)) return;
  console.error(`Commit detenido: el mensaje no lleva prefijo de tipo.

  feat: algo nuevo          (sube 1.4.2 → 1.5.0)
  fix:  ajuste              (sube 1.4.2 → 1.4.3)
  chore: datos              (no sube)
  feat!: o fix!: rompe      (sube 1.4.2 → 2.0.0)

Mensaje recibido: "${linea}"`);
  process.exit(1);
}

function subir(version, tipo, rompe) {
  const [M, m, p] = version.split('.').map(Number);
  if (rompe) return `${M + 1}.0.0`;
  if (tipo === 'feat') return `${M}.${m + 1}.0`;
  return `${M}.${m}.${p + 1}`;
}

function postCommit() {
  if (process.env.VERSIONANDO) return;
  // En un rebase o un cherry-pick el --amend reescribiría commits ajenos al que se está haciendo.
  if (['rebase-merge', 'rebase-apply', 'CHERRY_PICK_HEAD'].some(f => fs.existsSync(path.join(gitDir, f)))) return;

  const asunto = git('log', '-1', '--format=%s');
  const t = asunto.match(PREFIJO);
  if (!t || t[1] === 'chore') return;

  const fVersion = path.join(raiz, 'VERSION');
  const fLog = path.join(raiz, 'CHANGELOG.md');
  const anterior = fs.existsSync(fVersion) ? fs.readFileSync(fVersion, 'utf8').trim() : '1.0.0';
  const nueva = subir(anterior, t[1], Boolean(t[3]));
  const fecha = git('log', '-1', '--format=%ad', '--date=short');

  fs.writeFileSync(fVersion, nueva + '\n');
  const log = fs.readFileSync(fLog, 'utf8');
  const corte = log.indexOf('\n## ');
  const entrada = `\n## ${nueva} (${fecha})\n\n${asunto}\n`;
  fs.writeFileSync(fLog, corte === -1 ? log + entrada : log.slice(0, corte) + entrada + log.slice(corte));

  git('add', fVersion, fLog);
  execFileSync('git', ['commit', '--amend', '--no-edit', '--no-verify'], {
    env: { ...process.env, VERSIONANDO: '1' },
    stdio: 'ignore',
  });
  git('tag', `v${nueva}`);
  console.log(`Versión ${anterior} → ${nueva}`);
}

const [modo, arg] = process.argv.slice(2);
if (modo === 'commit-msg') commitMsg(arg);
else if (modo === 'post-commit') postCommit();
else { console.error('Uso: version.js commit-msg <fichero> | post-commit'); process.exit(2); }
