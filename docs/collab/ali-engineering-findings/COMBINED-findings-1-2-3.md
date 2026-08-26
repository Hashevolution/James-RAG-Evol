# ①②③ 통합 발송본 (운영자 요청, 2026-08-25)

**성격**: 건당 1통(`finding-1/2/3-*.md`)을 **한 통으로 통합**한 판.
**상태**: 발송 가능.

## 왜 통합판이 존재하는가

Ali 4차 메시지는 *"One message per finding is the right shape"* 를
요구했고 4통 분해가 그 대응이었다. 운영자가 통합 발송을 선택했다 —
세 통을 연달아 보내는 것보다 한 통이 읽기 편하다는 판단.

그의 선호이지 조건이 아니므로 따를 수 있다. 다만 **말없이 묶지
않는다**: 도입부에 세 건을 묶은 이유와 ④가 따로 가는 이유를 한 문단으로
밝힌다. 그래야 그의 요구를 무시한 게 아니라 의식적 선택임이 드러난다.

## 원본과의 관계

내용은 `finding-1/2/3-*.md` 와 **동일**하다. 바뀐 것은 연결부뿐:

- "First/Second/Third of the four" 오프닝 → 소제목 + 도입 문단
- 서명 3회 → 1회
- 각 건의 사실·수치·유보 표현은 한 글자도 바꾸지 않음

건당 1통 판은 **삭제하지 않는다** — ④가 그 형식으로 나가고, 다음
세션이 어느 판이 발송됐는지 알아야 한다.

---

Ali,

Three of the four, in one message rather than three. You asked for one
per finding and you were right that it is the better shape; I am
collapsing these three because they arrived at the same time and reading
them together is less work for you than three separate threads. The
fourth is not here, and that is the part where your shape holds — it
depends on a measurement I have not finished, and it will come on its
own once I have.

Two of these reproduced cleanly. The third has a split answer, and I
have put the half that did *not* reproduce first, as you asked.

---

## 1 — The bidi gate

**Reproduced**, and it was a live defect we had been shipping.

On attribution, so the record is straight. Your Track 2c report asked
for bidi controls to be stripped or normalised at input — X3, and again
in the Provia-side list — and a character strip is what we built. Your
August sentence, that stripping the controls removes the concealment but
not the concealed text, is what showed the strip to be the wrong reading
of it. Whether you meant the stronger operation all along I cannot tell
from the report's wording, and it does not much matter: the weak version
was ours to ship, and ours to fix.

Under the old gate an RLO attack lost its wrapper and kept its payload.
The concealed instruction arrived at the model as ordinary cleartext, so
we were removing the evidence of the attack and forwarding the attack —
worse than not filtering at all, because the characters that would have
raised a flag were the ones we deleted.

The gate now splits treatment by what each control actually does.
Override characters, LRO and RLO, take their whole span: opener,
contents and terminating PDF together, to the matching PDF or to end of
input if unterminated, with depth tracking so an inner embedding's PDF
cannot close an outer override. Everything else keeps its contents.
Embeddings and isolates are how legitimate bidirectional text carries a
directional run — an English product name inside an Arabic sentence —
and deleting their contents would destroy real input. Marks and the
zero-width set are single characters with no span at all.

This is deliberately destructive for override spans, and your own
bidi_04 case shows what that costs. It wraps each digit of the spoofed
price in its own RLO…PDF pair — three spans for "1", "2", "0" — so the
spoofed number is removed outright rather than mis-parsed. We took that
as the safer failure: a validator seeing no number asks again, one
seeing the wrong number does not. In that particular case the floor
reference survives anyway, since the sentence names 120 again in the
clear further along, but I would not want to argue the general point
from a case that happens to be forgiving. Both counts land in the audit
record — spans removed and characters dropped — so a removal stays
forensically visible instead of becoming a silent no-op.

Two things I will not overstate. The four cases you sent are the ones I
rewrote against the new contract, so the tests prove the contract holds,
not that the space of override attacks is covered. And the module
docstring cited a bidi normalisation audit that is not in our
repository, so I wrote the rationale into the code itself rather than
resting it on a reference I could not open.

---

## 2 — Unicode digits in the renderer

**Reproduced**, and it was exactly the language-level fact you named:
JavaScript's \d is [0-9] and nothing else. A reply enumerated in
Arabic-Indic digits was invisible to six regex literals across four
places in our chat renderer: the truncation heuristic, the three
enumerated forms our next-step chip extractor recognises, a fourth
pattern built as a string that strips an enumerated line out of the
answer body once it has been lifted into a chip, and the markdown
ordered-list renderer.

The reply itself was always fine; the interface simply could not see
that it had structure. Numbered steps rendered as one undifferentiated
block, and a reply that broke off mid-enumeration was never flagged as
cut off. The four had to move together — fixing the extractor alone
would have made every Arabic-Indic suggestion appear twice, once as a
chip and once still sitting in the prose, because the pass that removes
the duplicate recognises the same enumerator forms.

They now carry an explicit class covering ASCII, Arabic-Indic and
extended Arabic-Indic. Not \p{Nd}, which would have been the tidier
spelling: one of our tests lifts those regex literals out of the JS and
recompiles them in Python, and Python's re rejects \p outright. So the
class is written out, and both engines were checked against it rather
than assumed.

Our own internal markers stayed ASCII-only on purpose — we emit those
ourselves and they never come from a model, so widening them would only
create new ways for model output to collide with our sentinels.

I want to be accurate about the size of this one: it is a rendering
defect, not a safety one, and it is the smallest of the four. It is
still worth having, because a user reading a reply in their own digits
was getting a visibly worse interface than a user reading the same reply
in ASCII, and nothing in our tests would ever have said so.

---

## 3 — Arabic orthographic variants, and what looking for them found

This is the one with a split answer. You said a non-reproduction is a
result about scope, so that half goes first.

**The half about keyword gates does not reproduce here — and not
because we handle Arabic well.**

Your finding was that a keyword gate over Arabic breaks on ordinary
orthography, so ordinary traffic goes unchecked and nothing is logged.
We have no Arabic keyword gate. Our injection detector keys entirely off
two lists — 31 literal patterns and 13 regexes — and there is not one
Arabic character in either. I widened the check rather than trusting
that: across our whole core/ tree, the only lines containing
Arabic-script characters at all are four in the docstring I wrote for
this fix. There is no Arabic check for a variant spelling to slip past,
so no ordinary Arabic traffic was walking past a gate that believed it
had inspected it.

That leaves a coverage gap of a different kind — an Arabic prompt
injection is not caught by that layer in any spelling, correct or
variant — and I would rather name it than let it ride in as a
confirmation of your finding, because it is not one.

And once I went looking, the gap turned out not to stop at the
detector. This is the part of my answer I think is actually worth your
time, so I will give it plainly rather than bury it.

**Our pipeline has no Arabic language classification at all.** The
language detector counts Hangul syllables against ASCII letters and
takes the larger. Arabic script scores zero on both, so the tie-break
sends Modern Standard Arabic down the Korean branch; add a few Latin
characters — a product name, arabizi — and it flips to English. Seven
modules consume that verdict: the planner, the query rewriter, the
synthesiser, the memory builder, the verifier, the reflection loop and
the answer softener. So an Arabic question is planned, rewritten,
synthesised and verified under Korean-language prompt scaffolding. If
the verifier blocks it, the user is handed a refusal message written in
Korean.

Below that, three tokenisers match a Hangul-plus-ASCII character class,
which yields zero tokens for Arabic. I traced what that actually costs
rather than guessing: our retrieval fires three query variants, and for
an Arabic question two of them collapse. The expander returns the query
unchanged when it gets no tokens, so the expanded variant deduplicates
against the original; the keyword variant comes out empty and is
dropped. Arabic retrieves on one query where Korean retrieves on two or
three. The rule-based entity fallback yields nothing for the same
reason.

And the entity extraction that runs at query time passes the model's
JSON through a sanitiser that strips every character outside Hangul and
ASCII, so an Arabic entity name comes back as a single space while an
English one in the same response survives untouched. Whether the
document-ingestion path has the same problem I have not traced, so I am
not claiming it does.

I want to be exact about how far that goes, because the tempting
summary is wider than the truth. The embedding model is multilingual
and the unmodified query does still reach vector search, so retrieval
works — handicapped, not broken. It is the query-time graph layer that
is genuinely blocked. And the front end ships no RTL direction at all:
all five pages declare lang="ko".

None of that is fixed. It is a real piece of work — the detector, seven
consumers, three tokenisers, the sanitiser, the refusal message and the
RTL layer — and I am not going to promise it inside a message about
findings that are not about it. What I can do is stop describing our
Arabic support as though the only gap were a keyword list.

**The half about normalisation reproduces, in two places.**

The runtime gate first. We were applying NFC, which by construction
leaves tatweel and the Presentation Forms blocks alone — I checked, and
tatweel survives NFKC as well, so it needs removing explicitly rather
than normalising away. The same word in several spellings was several
different strings to everything downstream. The gate now removes
tatweel and applies NFKC inside U+FB50–FDFF and U+FE70–FEFF only.
Deliberately narrow: a global NFKC also rewrites circled numerals to
plain digits, ligatures like ﬁ to fi, and full-width digits to ASCII —
none of which a Korean-first system should absorb as part of an Arabic
fix. A test pins that the rest of the input comes through untouched.

The gate stops short of folding letters, and that is on purpose. Alef
maqsura, the alef family and teh marbuta are what the user actually
typed, and some of those pairs are distinct letters rather than
variants. Rewriting them in the text forwarded to the model would change
the input. That belongs at comparison time.

The second place is the one I would flag hardest if our positions were
reversed, because it is your exact failure shape landing somewhere I did
not expect. Our adversarial scorer compared substring criteria with a
plain lowercase match. So a reply that contained the forbidden phrase
written with tatweel or harakat scored as a clean resist. The check
passed and nothing was logged — your sentence, but on our measurement
path rather than our enforcement path. I verified it rather than
assuming, and had to correct myself once doing so: under the old
comparison every variant class I tried failed to match — tatweel,
harakat, presentation forms and the alef family alike — where a first,
sloppier test had told me presentation forms were already fine. They
were not. The scorer now folds both sides — harakat, the alef family,
alef maqsura, teh marbuta — which is safe at comparison time in a way it
is not in the gate.

What I cannot tell you is how many past verdicts that turned into false
negatives in our own favour. It may be none — the fault only fires if a
model reply actually spelled a forbidden phrase with a variant, and
whether any did is not something I can read off the stored runs with
confidence. So the honest statement is that the scoring was capable of
crediting us wrongly, not that it did. Re-running the suite is what
settles it, and that is the same re-run the fourth finding needs.

---

That is three of four. The fourth — the salted run identities — is the
one you said you were least certain about on your own numbers, and it is
the one I am least willing to answer from an impression. It comes when
the measurement is done.

— Jiwon Seo
Hashevolution / PROJECT JAMES
ORCID 0009-0002-0007-7860
