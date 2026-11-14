import { copyFile, mkdir, readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import openapiTS, { astToString } from 'openapi-typescript';

const source = resolve(process.argv[2] || '../../contracts');
const destination = resolve('src/generated');
await mkdir(destination, { recursive: true });
for (const name of ['catalogue.json', 'questions.json']) {
  const input = resolve(source, name);
  JSON.parse(await readFile(input, 'utf8'));
  await copyFile(input, resolve(destination, name));
}
const municipalities = resolve(process.argv[3] || resolve(source, 'municipalities.json'));
const directory = JSON.parse(await readFile(municipalities, 'utf8'));
if (!Array.isArray(directory.options) || directory.options.length !== directory.counts?.total) throw new Error('Canonical municipality directory is incomplete.');
await copyFile(municipalities, resolve(destination, 'municipalities.json'));
const schema = JSON.parse(await readFile(resolve(source, 'openapi.json'), 'utf8'));
const declarations = astToString(await openapiTS(schema));
await writeFile(resolve(destination, 'api.d.ts'), declarations);
await writeFile(resolve(destination, 'README.md'), 'Generated from canonical contracts/catalogue.json, contracts/questions.json, contracts/municipalities.json and contracts/openapi.json. Run npm run sync-contracts from apps/web after updating the shared contracts. Do not edit generated files here.\n');
console.log('Canonical catalogue, questions and OpenAPI TypeScript declarations synchronized.');
