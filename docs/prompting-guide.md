# How to get good answers out of Laya

Measured over 93 configurations against 300 blind labelled emails. Tuning used one
half. Every number below is from the other half, which the tuning never saw.

## The shape that works

1. **One binary question for each class.** Do not use one choice question with nine
   options. The model shares 192 tokens between all options, so nine options starve
   each other. Nine separate `noul` questions gave 59% against 47% for the choice.
2. **Take the raw argmax over the questions.** Do not calibrate each probability to a
   percentile first. Raw argmax gave 61%, percentile calibration 51%.
3. **Send a small object, not a wall of text.** `{from, subject, body}` with the body
   cut to 500 characters. The sender is worth 4 points. Dropping quoted replies,
   stripping URLs and removing footers made no difference.
4. **Ask about the email, not about the sender.** "Is this email about a parcel?"
   scores 62%. "Is the sender a courier?" scores 34%, which is the baseline.
5. **Keep each question short and concrete.** One word options scored 33%. Long
   descriptions scored 37%. One clear sentence scored 62%.

## The questions

```python
QUESTIONS = {
    "MONEY":     "Is this email about an invoice, a payment, a receipt or banking?",
    "DELIVERY":  "Is this email about a parcel, a courier or a shipment?",
    "SCHOOL":    "Is this email about a child or a school?",
    "WORK":      "Is this email from a colleague or a client about a job in hand?",
    "HEALTH":    "Is this email about health, a doctor or a therapist?",
    "FAMILY":    "Is this email from a friend or a relative about personal life?",
    "ADMIN":     "Is this email about an account, a password or a government body?",
    "MARKETING": "Is this email an advert, an offer or a promotion?",
}
```

Each is a `noul` question. The answer with the highest probability wins.

## Use the margin, not the probability

The gap between the best and the second best answer says how much to trust it. The
probability on its own does not.

| Margin at least | Share of mail answered | Accuracy on those |
|---|---|---|
| 0.00 | 100% | 65% |
| 0.05 | 70% | 74% |
| 0.10 | 49% | 84% |
| 0.15 | 34% | 90% |

With one margin for each class, tuned for 90% precision:

**Laya answers 24% of all mail and is right 94% of the time. It passes the rest on.**

| Class | Margin needed | Answered | Correct |
|---|---|---|---|
| `DELIVERY` | 0.00 | 18 | **100%** |
| `MONEY` | 0.18 | 5 | **100%** |
| `SCHOOL` | 0.02 | 5 | **100%** |
| `MARKETING` | 0.10 | 8 | 75% |
| `WORK`, `ADMIN`, `FAMILY`, `HEALTH` | never reaches 90% | 0 | - |

`DELIVERY` needs no margin at all. Whenever it wins, it is right.

## What Laya cannot do

The `action` dimension is hopeless. It answers `REPLY` for two thirds of all mail
whatever the text says, on both checkpoints and from any option order. The best
arrangement scored 65% against a 63% baseline, which is one email in fifty better than
always answering `READ`.

| Dimension | Best score | Baseline |
|---|---|---|
| topic | **65%** | 34% |
| action | 65% | 63% |
| urgency | 26% | 87% |
| sender | 57% | 63% |

Ask Laya what an email is about. Do not ask it what to do about it.
