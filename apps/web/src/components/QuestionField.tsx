'use client';
import { RadioList, RadioListItem } from '@astryxdesign/core/RadioList';
import { TextInput } from '@astryxdesign/core/TextInput';
import { TextArea } from '@astryxdesign/core/TextArea';
import type { ISODateString } from '@astryxdesign/core/Calendar';
import { DateInput } from '@astryxdesign/core/DateInput';
import type { Question } from '@/lib/catalogue';

export function QuestionField({ question, value, onChange, error, isDisabled }: { question: Question; value?: string; onChange: (value: string) => void; error?: string; isDisabled?: boolean }) {
  const common = {
    label: question.label,
    description: question.description || undefined,
    isRequired: question.required,
    isDisabled,
    status: error ? { type: 'error' as const, message: error } : undefined,
  };
  if (question.type === 'select' && question.options) return <RadioList {...common} value={value || ''} onChange={onChange}>
    {question.options.map(option => <RadioListItem key={option.value} value={option.value} label={option.label} />)}
  </RadioList>;
  if (question.type === 'date') return <DateInput {...common} value={(value || undefined) as ISODateString | undefined} onChange={next => onChange(next || '')} hasClear max={new Date().toLocaleDateString('en-CA') as ISODateString} />;
  if (question.type === 'textarea') return <TextArea {...common} value={value || ''} onChange={onChange} rows={4} maxLength={question.maxLength ?? undefined} />;
  return <TextInput {...common} value={value || ''} onChange={onChange} />;
}
