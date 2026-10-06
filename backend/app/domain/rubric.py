EMAIL_RUBRIC = """\
Score the email holistically from 0 to 5, then explain the evidence for each criterion.

Criteria:
- task_completion: Does the email address all three requirements with relevant detail?
- organization: Are ideas ordered logically with clear connections between them?
- language_use: How accurate and varied are grammar and vocabulary? Do errors obscure meaning?
- tone_and_register: Is the tone suitable for the recipient and the situation?

Score levels:
5 - All requirements are handled fully and clearly. Ideas connect smoothly. Grammar and
    vocabulary are varied and precise, with at most minor slips. Tone fits the recipient.
4 - All requirements are handled, one perhaps briefly. Organization is clear. A few errors
    appear but never block meaning. Tone is mostly appropriate.
3 - Most requirements are handled, some thinly. Connections are sometimes unclear. Noticeable
    errors or limited vocabulary occasionally make meaning harder to follow.
2 - Several requirements are missing or underdeveloped. Organization is weak. Frequent errors
    often make meaning unclear. Tone may be off.
1 - Little of the task is addressed. Few ideas are connected. Serious errors make most of the
    email hard to understand.
0 - Blank, off-topic, not in English, or copied from the prompt.

Example A (score 5):
Situation: A classmate borrowed your notes and has not returned them before the exam.
"Hi Jordan, I hope your week is going well. I'm writing about the biology notes I lent you
last Tuesday. Our exam is on Friday, so I'd really like to review them this weekend. Could you
bring them to the library on Thursday afternoon? If that doesn't work, I can pick them up from
your dorm instead. Also, if you found them useful, I'd be happy to study together before the
exam. Just let me know what suits you. Thanks, and good luck with your preparation! Best, Sam"
Why 5: every requirement is covered with specifics, the sequence is logical, language is
accurate and natural, and the friendly tone suits a classmate.

Example B (score 2):
Situation: Same as Example A.
"Hello. I give you my note last week. I need it because exam. Please you give me back fast.
Thank you."
Why 2: the request is present but the other requirements are missing, there is almost no
development, and repeated grammar errors (verb tense, missing words) weaken clarity.
"""
