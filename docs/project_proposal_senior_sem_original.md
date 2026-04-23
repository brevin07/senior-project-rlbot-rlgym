## Page 1

Brevin  Tating  btating@westmont.edu CS-195  Senior  Seminar  Mike  Ryu  
Rocket  Coach   
OVERVIEW  -  RocketCoach  is  an  automated,  AI-driven  training  platform  designed  to  bridge  the  gap  
between
 
novice
 
and
 
competitive
 
Rocket
 
League
 
players.
 
Unlike
 
traditional
 
static
 
bots,
 
RocketCoach
 
utilizes
 
Deep
 
Reinforcement
 
Learning
 
(Proximal
 
Policy
 
Optimization)
 
to
 
create
 
and
 
use
 
adaptive
 
training
 
agents
 
capable
 
of
 
mimicking
 
high-level
 
human
 
mechanics,
 
such
 
as
 
shadow
 
defense
 
or
 
dribbling.
 
 
 
MOTIVATION  -  Rocket  League  creates  a  uniquely  high  skill  ceiling  due  to  its  physics-based  mechanics,  
often
 
requiring
 
thousands
 
of
 
hours
 
for
 
players
 
to
 
reach
 
any
 
sort
 
of
 
“competitiveness”.
 
While
 
human
 
coaching
 
exists,
 
it
 
is
 
not
 
accessible
 
to
 
most
 
players
 
and
 
can
 
get
 
very
 
expensive.
 
Existing
 
bots
 
are
 
either
 
trivial
 
to
 
beat
 
or
 
simply
 
made
 
for
 
looks,
 
performing
 
superhuman-level
 
inputs
 
that
 
do
 
not
 
resemble
 
realistic
 
human
 
play.
 
RocketCoach
 
provides
 
high-level
 
instruction
 
by
 
servicing
 
an
 
always-available,
 
data-driven
 
opponent
 
that
 
evolves
 
with
 
the
 
player’s
 
skill
 
level.
 
 
 
PROBLEM  STATEMENT  -  Aspiring  Rocket  League  competitive  players  lack  accessible,  consistent  training  tools.  
They
 
cannot
 
practice
 
“defending
 
a
 
dribble”
 
or
 
“challenging
 
an
 
air
 
dribble”
 
on
 
demand
 
because
 
no
 
current
 
bot
 
performs
 
these
 
actions
 
consistently
 
in
 
a
 
realistic
 
way.
 
This
 
forces
 
players
 
to
 
rely
 
on
 
ranked
 
matchmaking
 
games,
 
which
 
is
 
inefficient
 
for
 
training
 
specific
 
skills
 
the
 
player
 
needs
 
to
 
work
 
on.

## Page 2

PROPOSED  SOLUTION  
-  Diagnosis :  A  Python  backend  utilizing  the  rocket  utility  to  parse  raw  replay  binaries  into  
telemetry
 
data,
 
identifying
 
specific
 
mechanical
 
flaws.
 
 -  Prescription :  A  logic  engine  that  maps  these  statistics  to  specific  training  agents  (e.g.,  
“Bad
 
Shadow
 
Defense”
 
→
 
“Late
 
Flick
 
Bot”)
 -  Training :  An  offline  training  session  against  a  custom  PPO-trained  agent  that  has  been  
reward-shaped
 
to
 
specifically
 
exploit
 
the
 
user’s
 
weakness,
 
forcing
 
them
 
to
 
adapt
 
(e.g.,
 
a
 
“Shadow
 
Defense”
 
bot
 
that
 
dribbles
 
consistently
 
without
 
flicking
 
early).
 
 
SPECIFICATIONS  
-  Replay  Analysis:  A  Python  interface  using  the  rrrocket  utility  to  fetch  JSON  telemetry.  It  
will
 
calculate
 
derived
 
metrics
 
to
 
categorize
 
a
 
user's
 
skills.
 
These
 
metrics
 
will
 
be
 
saved
 
to
 
a
 
SQL
 
database,
 
so
 
the
 
script
 
can
 
see
 
how
 
the
 
user’s
 
skills
 
change
 
over
 
time.
 -  AI-Opponent  Structure  -  Reward  Engineering:  Custom  “Coach  Rewards”  that  punish  random  movements  
and
 
sequences
 
and
 
reward
 
controlled
 
interactions
 
(dribbles,
 
keeping
 
possession),
 
forcing
 
the
 
bot
 
to
 
play
 
in
 
a
 
way
 
that
 
teaches
 
a
 
human
 
opponent.
 -  Checkpoints:  A  version  control  system  for  model  checkpoints  to  offer  “Difficulty  
Tiers”
 
for
 
the
 
user
 
to
 
play
 
against.
 -  User  Dashboard  (Streamlit):  A  local  web-interface  where  users  can  log  in  and  input  
their
 
replay
 
files,
 
view
 
their
 
game
 
report,
 
and
 
click
 
a
 
single
 
button
 
to
 
launch
 
the
 
recommended
 
training
 
bot.
 
 
JUSTIFICATIONS  -  Novelty:  While  replay  analysis  tools  exist,  and  ML  bots  exist,  no  public  tool  
integrates
 
them.
 
Currently,
 
a
 
player
 
must
 
manually
 
analyze
 
a
 
replay,
 
guess
 
what
 
they
 
need
 
to
 
work
 
on,
 
and
 
then
 
find
 
a
 
training
 
pack.
 
RocketCoach
 
automates
 
this
 
“Coach’s
 
Workflow,”
 
providing
 
a
 
tailored,
 
data-driven
 
practice
 
routine
 
that
 
previously
 
required
 
a
 
human
 
to
 
design.
 -  Feasibility :   -  Data  Ingestion :  The  rrrocket  utility  is  public  and  well-documented,  as  
well
 
as
 
providing
 
telemetry
 
data
 
of
 
all
 
players
 
throughout
 
the
 
whole
 
game.

## Page 3

-  Bot  Training :  During  Sprint  0,  I  successfully  set  up  the  Linux/WSL  
environment
 
for
 
RLGym-PPO
 
and
 
verified
 
that
 
I
 
can
 
train
 
agents
 
at
 
>50,000
 
steps
 
per
 
second.
 
 -  Integration :  The  “glue”  code  (Python  scripts  launching  RLBot)  is  a  
straightforward
 
process,
 
minimalizing
 
project
 
structure
 
risk.
 -  Cost :  This  project  relies  mostly  on  open-source  software  (Python,  PyTorch,  
RLGym).
 
The
 
only
 
monetary
 
cost
 
would
 
be
 
access
 
to
 
OpenAI’s
 
Codex
 
models
 
(or
 
alternative
 
code-generation
 
APIs)
 
if
 
utilized
 
to
 
dynamically
 
generate
 
explanations
 
or
 
heuristic
 
logic.
 
This
 
social
 
cost
 
is
 
positive,
 
as
 
the
 
tool
 
provides
 
a
 
free,
 
scalable
 
alternative
 
to
 
expensive
 
human
 
coaching
 
services. 
MILESTONES  
 -  Mission  Statement :  “Engineer  an  intelligent,  closed-loop  coaching  system  that  analyzes  
player
 
data
 
to
 
provide
 
personalized,
 
AI-driven
 
training
 
sessions,
 
accelerating
 
the
 
path
 
to
 
expertise
 
for
 
Rocket
 
League
 
players.”
  -  OKRs :   -  Milestone  1:  Alpha  Release  (The  “Diagnosis”  Phase)  -  Objective :  Provide  users  with  an  immediate,  data-backed  look  into  their  
fundamental
 
mechanical
 
flaws
 
using
 
standard
 
heuristic
 
analysis.
 -  KR  1 :  System  successfully  parses  and  extracts  telemetry  from  
100%
 
of
 
valid
 
standard
 
.replay
 
files
,
 
into
 
a
 
queryable
 
Pandas
 
structure.
 
 -  KR  2 :  Develop  an  algorithm  that  accurately  flags  3  specific  
player
 
weaknesses
 
based
 
on
 
statistical
 
thresholds.
 -  KR  3 :  The  3D  Replay  Visualizer  renders  player  positions  at  >30  
FPS
 
within
 
the
 
application,
 
successfully
 
pausing
 
at
 
identified
 “Mistake  Timestamps”  without  crashing.  (Similar  to  Chess.com match  replays)  -  KR  4 :  SQL  database  successfully  stores  and  queries  user  stats  for  
100%
 
of
 
logged
 
sessions
.
 
   -  Milestone  2:  Beta  Release  (The  “Training”  Phase)  -  Objective :  Engineer  the  Training  Partners  -  KR  1 :  Train  a  “Possession  Bot”  (using  custom  reward  shaping)  
that
 
maintains
 
ball
 
control
 
for
 
>3.0s
 
on
 
average
,
 
designed
 
to
 
tell
 
the
 
user
 
Shadow
 
Defense.

## Page 4

-  KR  2 :  Train  an  “Aggression  Bot”  (rewarding  high  velocity  and  
shots)
 
that
 
maintains
 
>50%
 
time
 
at
 
supersonic
 
speed
 
and
 
challenges
 
the
 
ball
 
within
 
3s
 
of
 
possession
 
changes
,
 
designed
 
to
 
teach
 
the
 
user
 
faster
 
decision
 
making.
 -  KR  3 :  Implement  a  “Model  Selector”  script  that  can  instantly  
swap
 
these
 
bot
 
behaviors
 
in
 
the
 
game
 
client
 
based
 
on
 
the
 
user’s
 
Replay
 
Analysis
 
result.
   -  Milestone  3:  Release  Candidate  (The  “Growth”  Phase)  -  Objective :  Deliver  a  frictionless  “Upload-to-Improvement”  loop  that  
validates
 
user
 
progress
 
and
 
encourages
 
long-term
 
retention.
 -  KR  1 :  System  processes  a  standard  replay  and  renders  the  full  
dashboard
 
in
 
<10
 
seconds
,
 
ensuring
 
the
 
tool
 
is
 
fast
 
enough
 
for
 
use
 
between
 
matches.
 -  KR  2 :  In  a  user  study  of  3+  Rocket  League  players,  100%  of  
participants
 
identify
 
a
 
game-losing
 
habit
 
they
 
were
 
previously
 
unaware
 
of.
  
 -  KR  3 :  The  system  successfully  correlates  data  from  multiple  
replays
 
to
 
generate
 
a
 
“Trend
 
Graph,”
 
accurately
 
displaying
 
%
 
improvement
 
in
 
specific
 
metrics
 
across
 
a
 
user’s
 
upload
 
history.
 
  -  Grading  Criteria :  I  will  be  using  grading  criteria  for  every  non-binary  task,  as  all  binary  
tasks
 
should
 
be
 
either
 
a
 
pass
 
or
 
fail.
 
  -  M1  KR2 :   -  A :  Algorithm  flags  flaws  with  >90%  agreement  against  manual  
human
 
review.
 -  B :  >80%  agreement.  -  C :  >70%  agreement,  sometimes  flags  false  positives.  -  D :  <50%  agreement,  effectively  random  guessing.  -  F :  Algorithm  fails  to  flag  obvious  errors.    -  M2  KR1 :   -  A :  Maintains  ball  controls  >4.0s  avg:  actively  flicks  to  avoid  
challenges.
 -  B :  >3.0s  avg;  consistently  keeps  ball  on  car.   -  C :  >1.5s  avg;  can  dribble  but  drops  it  often  -  D :  <1.0s  avg;  mostly  pushed  the  ball  away  -  F :  Bot  cannot  dribble/control  ball

## Page 5

-  M2  KR2 :   -  A :  >60%  supersonic  time;  challenges  instantly  (<2s)  -  B :  >50%  supersonic  time;  challenges  instantly  (<3s)  -  C :  >30%  supersonic  time;  hesitation  in  challenges  -  D :  <10%  supersonic  time;  plays  passively  -  F :  Bot  stays  in  net/drives  slowly    -  M2  KR3 :   -  A:  Fully  automatic;  dashboard  click  instantly  loads  bot  in  game  
without
 
restart
 -  B:  Semiautomatic;  dashboard  click  updates  config;  user  must  
restart
 
match
 -  C:  Manual:  user  must  manually  copy  config  files  -  D:  Broken;  script  fails  to  swap  models  -  F:  No  integration   -  M3  KR1 :   -  A:  Full  analysis  &  render  in  <5  seconds  -  B:  Full  analysis  &  render  in  <10  seconds  -  C:  Full  analysis  &  render  in  <30  seconds  -  D:  Full  analysis  &  render  in  >1  minute  -  F:  System  times  out/crashes   -  M3  KR3 :   -  A:  Interactive  charts  showing  history  +  %  improvement  trends  -  B:  Static  line  graph  showing  improvement  over  time  -  C:  Simple  text  table  comparing  “Now”  vs  “Then”  -  D:  Raw  list  of  past  stats  only  -  F:  No  historical  tracking    Credits/Acknowledgements :  Dominic  Tating,  Dan  Shank,  Mike  Ryu
