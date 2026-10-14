import type { Session } from './App'

export function englishExample(base: Session): Session {
  const turns = [
    ['opponent', 'You are unwilling to help again. Does the team matter to you at all?'],
    ['player', 'The team matters. I am unavailable after 19:00. Let us discuss options without judging my loyalty.'],
    ['opponent', 'The contractor arrives at 19:30. Who will accept the work?'],
    ['player', 'I can prepare the documents and checklist by 18:30. Could Marina meet the contractor?'],
    ['opponent', 'Yes, but she will need a list of what to check.'],
    ['player', 'I will send it to both of you by 18:30. We can discuss any questions before I leave.'],
    ['opponent', 'Agreed. I will contact Marina and confirm the time.'],
  ] as const
  return { ...base, settings: { ...base.settings, language: 'en' },
    case: { ...base.case, title: 'An extra shift',
      context: 'Your manager asks you to stay late to accept a contractor’s work. You already have plans, and the discussion has turned into an assessment of your loyalty to the team.',
      student_role: 'Project coordinator', negotiation_topic: 'Who will meet the contractor this evening and how to prepare the handover.',
      player_conflict_goal: 'Discuss declining an extra shift without questioning my loyalty to the team.',
      known_facts: ['The contractor arrives at 19:30.', 'You can prepare the documents by 18:30.', 'Marina is another team member. She works on the project and knows the contractor.'],
    }, opponent: { name: 'Alex', role: 'Project manager' },
    messages: turns.map(([speaker, text], index) => ({ id: `example-${index}`, speaker, text, created_at: base.created_at, delivery_status: 'sent' })),
  }
}

export const englishReport: NonNullable<Session['debrief']> = {
  summary: 'The dialogue began with an accusation of disloyalty. You stated your time boundary and brought the discussion back to who would meet the contractor. The conversation ended with a concrete handover plan.',
  strengths: [
    { quote: 'Let us discuss options without judging my loyalty.', explanation: 'You named the unwanted way of speaking and proposed continuing the practical discussion, keeping an agreement possible.' },
    { quote: 'I can prepare the documents and checklist by 18:30.', explanation: 'You offered a manageable contribution with a clear deadline. This moved the discussion towards organising the work.' },
  ],
  risks: [{ quote: 'Could Marina meet the contractor?', explanation: 'You proposed this as a question rather than a promise on Marina’s behalf. Her confirmation is still needed to complete the agreement.' }],
  next_step: 'Clarify how Marina’s participation will be confirmed. Ask one question and wait for the answer before discussing other details.',
  example_phrase: 'I will send the checklist by 18:30. How will we confirm the meeting time with Marina?',
}
