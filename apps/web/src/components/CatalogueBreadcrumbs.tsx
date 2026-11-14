'use client';
import { Breadcrumbs, BreadcrumbItem } from '@astryxdesign/core/Breadcrumbs';
import type { CatalogueNode } from '@/lib/catalogue';

export function CatalogueBreadcrumbs({ trail, suffix }: { trail: CatalogueNode[]; suffix?: string }) {
  // Keep long trails readable by showing the category and the last two choices.
  const indices = trail.length > 3 ? [0, ...trail.slice(-2).map((_, i) => trail.length - 2 + i)] : trail.map((_, i) => i);
  return <Breadcrumbs label="Report path" variant="supporting">
    <BreadcrumbItem href="/report" isCurrent={false}>Report a problem</BreadcrumbItem>
    {indices.map(i => <BreadcrumbItem key={trail[i].id} href={'/report/' + trail.slice(0, i + 1).map(node => node.slug).join('/')} isCurrent={!suffix && i === trail.length - 1}>{trail[i].label}</BreadcrumbItem>)}
    {suffix ? <BreadcrumbItem isCurrent>{suffix}</BreadcrumbItem> : null}
  </Breadcrumbs>;
}
