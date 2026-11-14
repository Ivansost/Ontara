import source from '@/generated/municipalities.json';

export type MunicipalityOption = {
  id: string;
  label: string;
  name: string;
  tier: 'lower' | 'single' | 'upper';
  type: string;
  upperTierId: string | null;
  upperTierName: string | null;
  geographicArea: string;
  aliases: string[];
};
export const municipalityDirectory = source as { version: number; counts: { total: number; lowerTier: number; singleTier: number; upperTier: number }; options: MunicipalityOption[] };
export const municipalityById = new Map(municipalityDirectory.options.map(option => [option.id, option]));
const searchable = (option: MunicipalityOption) => ({ value: option.id, label: [option.label, option.name, ...option.aliases, option.geographicArea].join(' ') });
export const municipalitySelectorOptions = [
  { type: 'section' as const, title: 'Regions and counties', options: municipalityDirectory.options.filter(option => option.tier === 'upper').map(searchable) },
  { type: 'section' as const, title: 'Municipalities', options: municipalityDirectory.options.filter(option => option.tier !== 'upper').map(searchable) },
  { value: 'other', label: 'Enter a municipality manually' },
];
