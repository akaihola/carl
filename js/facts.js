// Facts parsing and verification queue management
window.Carl = window.Carl || {};

Carl.facts = {
    // Track which number to assign to next fact
    nextNumber: 1,

    // Parse Qn:/An: format from model output and manage facts
    parseAndStore(text) {
        const { state } = Carl;
        const lines = text.split('\n');

        for (const line of lines) {
            const trimmed = line.trim();

            // Match Qn: format (Q followed by number and colon)
            const questionMatch = trimmed.match(/^Q(\d+):\s*(.+)$/);
            if (questionMatch) {
                const number = parseInt(questionMatch[1], 10);
                const question = questionMatch[2];
                this.nextNumber = Math.max(this.nextNumber, number + 1);

                if (state.facts.mapping[number]) {
                    // Question already exists - this might be an update
                    console.log(`[FACTS] Question ${number} already exists`);
                } else {
                    // New question - store it and wait for answer
                    state.facts.mapping[number] = { q: question, a: null, f: null };
                    console.log(`[FACTS] Parsed Q${number}: ${question}`);
                }
            }

            // Match An: format (A followed by number and colon)
            const answerMatch = trimmed.match(/^A(\d+):\s*(.+)$/);
            if (answerMatch) {
                const number = parseInt(answerMatch[1], 10);
                const answer = answerMatch[2];
                this.nextNumber = Math.max(this.nextNumber, number + 1);

                if (state.facts.mapping[number]) {
                    const prevAnswer = state.facts.mapping[number].a;
                    state.facts.mapping[number].a = answer;
                    state.facts.mapping[number].f = null;  // Reset fact for re-verification

                    if (prevAnswer !== answer) {
                        // Answer was updated - move to head of queue if not currently verifying
                        if (state.facts.currentVerification !== number) {
                            state.facts.queue = state.facts.queue.filter(n => n !== number);
                            state.facts.queue.unshift(number);
                            console.log(`[FACTS] Updated A${number}: "${answer}" (moved to head of queue)`);
                        } else {
                            console.log(`[FACTS] Updated A${number}: "${answer}" (currently verifying)`);
                        }
                    } else {
                        console.log(`[FACTS] Parsed A${number}: ${answer}`);
                    }
                } else {
                    // Answer without question - create placeholder
                    state.facts.mapping[number] = { q: `Question ${number}`, a: answer, f: null };
                    state.facts.queue.push(number);
                    console.log(`[FACTS] Parsed A${number} (no Q${number} yet): ${answer}`);
                }

                // Ensure this fact is in the queue if not already verifying
                if (!state.facts.queue.includes(number) && state.facts.currentVerification !== number) {
                    state.facts.queue.push(number);
                }
            }
        }
    },

    // Check if text contains Qn:/An: format
    hasFactFormat(text) {
        return /^Q\d+:/.test(text.trim()) || /^A\d+:/.test(text.trim());
    },

    // Filter out Qn:/An: format from text (for display)
    filterFactLines(text) {
        const lines = text.split('\n');
        return lines.filter(line => {
            const trimmed = line.trim();
            return !/^Q\d+:/.test(trimmed) && !/^A\d+:/.test(trimmed);
        }).join('\n');
    }
};
