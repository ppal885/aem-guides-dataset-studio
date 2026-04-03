Map Cyclic References
====================

Structure:
- map_a.ditamap: topicref to topic_a.dita, mapref to map_b.ditamap
- map_b.ditamap: topicref to topic_b.dita, mapref to map_a.ditamap

Cycle: map_a -> map_b -> map_a

Open map_a.ditamap as the root. Processors may warn about or reject the cyclic mapref.
