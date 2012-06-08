This document briefly describes the BGs plugin.


== Commands ==

bg - tag a message as a glucose result

bgoops - untag your previously tagged result

bgoptin - opt in to sqlite tracking by user

bgoptout - opt out of sqlite tracking by user and delete stored results from the database

last, lastbgs - request stored results

esta1c, ea1c - estimates an A1C given an average blood sugar

estbg, eag, ebg - etimates an average blood sugar given an A1C


== Variables ==

defaultLastBGCount - number of readings with which to reply when not specified in a parameter to last/lastbgs

measurementTransitionValue - assumption threshold for differentiating between mmol/L and mg/dL

measurementTransitionValueA1C - assumption threshold for differentiating between DCCT % and mmol/mol
