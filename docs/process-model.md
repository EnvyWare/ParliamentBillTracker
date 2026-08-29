# The process model

This is the model the flow diagram is drawn from. It is the design source for
`frontend/src/model/routes.ts`: if the two ever disagree, this document is
what should be argued about first and the code changed to match.

It describes the passage of a Public Bill as set out in Parliament's own
guidance. It is deliberately a model, not a complete account of procedure —
the notes at the end record what is left out and why.

## The full route

```mermaid
flowchart TD
    START(["Bill introduced"]) --> FR1["1 · First Reading<br/>formal, no debate"]
    FR1 --> SR1["2 · Second Reading<br/>the main debate on the principle"]

    SR1 --> V1{"Does the House agree<br/>the principle?"}
    V1 -- "No" --> FALL(["Bill falls"])
    V1 -- "Yes" --> MONEY[/"Money resolution<br/>only if the Bill commits public spending"/]

    MONEY --> CT{"Which committee?"}
    CT -- "Most Bills" --> PBC["3 · Public Bill Committee<br/>line by line"]
    CT -- "Constitutional or urgent" --> CWH["3 · Committee of the whole House"]
    CT -- "Rare" --> SEL["3 · Select Committee"]

    PBC --> AM1{"Was the Bill amended<br/>in committee?"}
    CWH --> AM1
    SEL --> AM1

    AM1 -- "No" --> TR1
    AM1 -- "Yes" --> RS1["4 · Report Stage<br/>the whole House reviews the changes"]
    RS1 --> TR1["5 · Third Reading<br/>the final text in this House"]

    TR1 --> V2{"Does the House<br/>pass the Bill?"}
    V2 -- "No" --> FALL
    V2 -- "Yes" --> HANDOVER[/"Passes to the second House"/]

    HANDOVER --> FR2["6 · First Reading"]
    FR2 --> SR2["7 · Second Reading"]
    SR2 --> V3{"Does the second House<br/>agree the principle?"}
    V3 -- "No" --> FALL
    V3 -- "Yes" --> CS2["8 · Committee Stage"]
    CS2 --> RS2["9 · Report Stage"]
    RS2 --> TR2["10 · Third Reading"]

    TR2 --> AM2{"Did the second House<br/>change the Bill?"}
    AM2 -- "No" --> RA["12 · Royal Assent"]
    AM2 -- "Yes" --> PP["11 · Consideration of Amendments"]

    PP --> AGREE{"Do both Houses now<br/>agree the same text?"}
    AGREE -- "No, another exchange" --> PP
    AGREE -- "Yes" --> RA

    RA --> ACT(["Act of Parliament"])

    ENDSESSION{{"The session ends before<br/>the Bill has finished"}} --> CARRY{"Is a carry-over<br/>motion agreed?"}
    CARRY -- "Yes" --> NEXT(["Continues in the next session"])
    CARRY -- "No" --> FALL

    WITHDRAW{{"The Bill is withdrawn"}} --> FALL
```

## What each shape means

| Shape | Meaning | Holds Bills? |
| --- | --- | --- |
| Rounded terminal | A start or end state | No |
| Rectangle | A numbered stage on the route | Yes |
| Parallelogram | A procedural step that runs alongside the route | No |
| Diamond | A decision that can send the Bill more than one way | No |
| Hexagon | Something that can happen at any point, not at one step | No |

The twelve numbered rectangles are the only places a Bill is ever counted.
That is what keeps the counts on the main chart and the sections it renders
in agreement: every Bill is at exactly one numbered stage, or is explicitly
unclassified.

## Decisions the model makes deliberately

**Committee type is a real branch, not a footnote.** The API distinguishes a
Public Bill Committee (stage 8) from a Committee of the whole House (49) and
a Select Committee (43). All three normalise to the same numbered stage, so a
Bill is still counted once, but the branch is drawn because which committee a
Bill goes to is a genuine decision with visible consequences.

**Report stage can be skipped.** A Bill that came out of committee unamended
can go straight to third reading. Drawing report stage as unconditional would
make a Bill that skipped it look as though it had gone missing.

**Ping-pong is a loop.** Consideration of amendments is not one step the Bill
passes through; it is an exchange that repeats until the two Houses agree.
The published snapshot counts the exchanges, so the diagram can say which one
a Bill is currently in.

**Ending early is not a stage.** Withdrawal and running out of session time
can happen at almost any point. Drawing them as boxes on the route would
imply an order they do not have, so they hang off the side.

## What is left out, and why

- **The Parliament Acts.** The Commons can in principle pass a Bill without
  the Lords' agreement. It has happened a handful of times in a century, and
  the Bills API does not model it, so including it would add a path that is
  never taken in the data.
- **Private Bills and Hybrid Bills.** These have their own examination stages
  before the route proper. The published snapshot marks them as following a
  special procedure rather than pretending they fit here.
- **Lords Grand Committee and Special Public Bill Committee.** Both normalise
  to the Lords committee stage. They are shown by name on the Bill's own
  page, but they are not separate branches on the chart.
- **Commencement.** An Act is not necessarily in force on the day it receives
  Royal Assent. That is beyond what the Bills API describes.
- **Amendment content, votes and speeches.** Out of scope for the first
  release, as recorded in the specification's non-goals.
