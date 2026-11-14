import { Button } from '@astryxdesign/core/Button';
import { FormLayout } from '@astryxdesign/core/FormLayout';
import { Heading } from '@astryxdesign/core/Heading';
import { HStack, VStack } from '@astryxdesign/core/Stack';
import { TextArea } from '@astryxdesign/core/TextArea';
import { TextInput } from '@astryxdesign/core/TextInput';

// A visual preview only: no draft state, input handlers, session or API calls.
// Astryx disabled/read-only controls also cover direct step links.
export function InactiveReportPreview() {
  return <VStack gap={5}>
    <Heading level={2}>Report details</Heading>
    <FormLayout>
      <TextInput label="Incident municipality" value="" placeholder="Municipality name" autoComplete="off" isDisabled />
      <TextInput label="Address or nearest intersection" value="" placeholder="Street address or intersection" autoComplete="off" isDisabled />
      <TextArea label="Describe the problem" value="" rows={4} autoComplete="off" isDisabled />
    </FormLayout>
    <HStack><Button label="Submit report" variant="primary" isDisabled /></HStack>
  </VStack>;
}
