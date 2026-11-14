import catalogueSource from '@/generated/catalogue.json';
import questionsSource from '@/generated/questions.json';

import type { components } from '@/generated/api';

// Required defaults reflect the complete canonical serialized snapshots.
export type CatalogueNode = Omit<Required<components['schemas']['CatalogueNode']>, 'children'> & { children: CatalogueNode[] };
export type DemoLocation = (typeof catalogueSource.demoLocations)[number];
export type Question = components['schemas']['Question'];
export type Questionnaire = components['schemas']['Questionnaire'];
export type Answers = Record<string, string>;
export const catalogue = catalogueSource as { version: string; categories: CatalogueNode[]; demoLocations: DemoLocation[]; disclaimer: string };
export const questionnaires: Record<string, Questionnaire> = questionsSource.issues as Record<string, Questionnaire>;
export const followUpQuestions: Record<string, Question> = questionsSource.followUp as Record<string, Question>;

export function resolvePath(segments: string[]): CatalogueNode[] | null {
  const trail: CatalogueNode[] = [];
  let nodes = catalogue.categories;
  for (const slug of segments) {
    const node = nodes.find(candidate => candidate.slug === slug);
    if (!node) return null;
    trail.push(node);
    nodes = node.children;
  }
  return trail;
}

export function issuePath(issueId: string): string | null {
  function find(nodes: CatalogueNode[], parents: string[]): string | null {
    for (const node of nodes) {
      const path = [...parents, node.slug];
      if (node.id === issueId) return `/report/${path.join('/')}`;
      const child = find(node.children, path);
      if (child) return child;
    }
    return null;
  }
  return find(catalogue.categories, []);
}

export function visibleQuestions(questions: Question[], answers: Answers): Question[] {
  return questions.filter(question => !question.visibleWhen || answers[question.visibleWhen.questionId] === question.visibleWhen.equals);
}

export function validateQuestions(questions: Question[], answers: Answers): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const question of visibleQuestions(questions, answers)) {
    const value = (answers[question.id] || '').trim();
    if (question.required && !value) errors[question.id] = 'Please answer this question.';
    else if (value && question.minLength && value.length < question.minLength) errors[question.id] = `Please enter at least ${question.minLength} characters.`;
    else if (question.maxLength && value.length > question.maxLength) errors[question.id] = `Please use ${question.maxLength} characters or fewer.`;
    else if (value && question.options && !question.options.some(option => option.value === value)) errors[question.id] = 'Choose one of the available options.';
  }
  return errors;
}
