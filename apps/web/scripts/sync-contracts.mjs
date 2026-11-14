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
const schema = JSON.parse(await readFile(resolve(source, 'openapi.json'), 'utf8'));
const declarations = astToString(await openapiTS(schema));
await writeFile(resolve(destination, 'api.d.ts'), declarations);
await writeFile(resolve(destination, 'README.md'), 'Generated from the backend-owned contracts/catalogue.json, contracts/questions.json and contracts/openapi.json. Run npm run sync-contracts from apps/web after updating the shared contracts. Do not edit generated files here.\n');
console.log('Canonical catalogue, questions and OpenAPI TypeScript declarations synchronized.');
