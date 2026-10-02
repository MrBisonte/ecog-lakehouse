# Data licence

Files under `docs/data/` are derived from the Stanford ECoG library: recordings from real patients who donated their time. The derived tables carry pseudonyms; the data will not be used to identify individuals.

## Licence

CC BY-SA 4.0, the licence of the source. Derivatives here carry the same licence; the full text is in `LICENSES/CC-BY-SA-4.0.txt`. The code that produced them is MIT, see `LICENSE`. Source repository: https://github.com/MrBisonte/ecog-lakehouse

## Cite the source

The dataset:

> Miller, Kai Joshua. (2016). A library of human electrocorticographic data and analyses. Stanford Digital Repository. Available at: https://purl.stanford.edu/zk881ps0522

The paper that describes it:

> Miller, K. J. A library of human electrocorticographic data and analyses. Nature Human Behaviour 3, 1225 to 1235 (2019). https://doi.org/10.1038/s41562-019-0678-3

The paper each experiment first appeared in, as its `README_<experiment>_dataset_notes` gives it:

| Experiment | Paper | DOI |
|---|---|---|
| `fingerflex` | Miller, Kai J., Dora Hermes, Christopher J. Honey, Adam O. Hebb, Nick F. Ramsey, Robert T. Knight, Jeffrey G. Ojemann, and Eberhard E. Fetz. "Human motor cortical activity is selectively phase-entrained on underlying rhythms." PLoS computational biology 8, no. 9 (2012): e1002655. | https://doi.org/10.1371/journal.pcbi.1002655 |
| `motor_basic` | Miller, Kai J., Eric C. Leuthardt, Gerwin Schalk, Rajesh PN Rao, Nicholas R. Anderson, Daniel W. Moran, John W. Miller, and Jeffrey G. Ojemann. "Spectral changes in cortical surface potentials during motor movement." Journal of Neuroscience 27, no. 9 (2007): 2424-2432. | https://doi.org/10.1523/JNEUROSCI.3886-06.2007 |
| `faces_basic` | Miller, Kai J., Gerwin Schalk, Dora Hermes, Jeffrey G. Ojemann, and Rajesh PN Rao. "Spontaneous decoding of the timing and content of human object perception from cortical surface recordings reveals complementary information in the event-related potential and broadband spectral change." PLoS computational biology 12, no. 1 (2016): e1004660. | https://doi.org/10.1371/journal.pcbi.1004660 |

Anatomical labels of the `faces_basic` electrodes follow Destrieux, C., Fischl, B., Dale, A. and Halgren, E. Automatic parcellation of human cortical gyri and sulci using standard anatomical nomenclature. NeuroImage 53, 1 to 15 (2010). https://doi.org/10.1016/j.neuroimage.2010.06.010

The same references are machine readable in `CITATION.cff`.

## Ethics statements

Each experiment's notes ask that any publication involving the data include its statement without modification. They are reproduced here verbatim, one per experiment used.

`fingerflex`:

> Ethics statement: All patients participated in a purely voluntary manner, after providing informed written consent, under experimental protocols approved by the Institutional Review Board of the University of Washington (#12193). All patient data was anonymized according to IRB protocol, in accordance with HIPAA mandate. These data originally appeared in the manuscript “Human Motor Cortical Activity Is Selectively Phase- Entrained on Underlying Rhythms” published in PLoS Computational Biology in 2012 [Reference].

`motor_basic`:

> Ethics statement: All patients participated in a purely voluntary manner, after providing informed written consent, under experimental protocols approved by the Institutional Review Board of the University of Washington (#12193). All patient data was anonymized according to IRB protocol, in accordance with HIPAA mandate. It was made available through the library described in “A Library of Human Electrocorticographic Data and Analyses” by Kai Miller [Reference], freely available at https://searchworks.stanford.edu/view/zk881ps0522. All patient data was anonymized according to IRB protocol, in accordance with HIPAA mandate. These data originally appeared in the manuscript “Spectral Changes in Cortical Surface Potentials during Motor Movement” published in Journal of Neuroscience in 2007 [Reference].

`faces_basic`:

> Ethics statement: All patients participated in a purely voluntary manner, after providing informed written consent, under experimental protocols approved by the Institutional Review Board of the University of Washington (#12193). All patient data was anonymized according to IRB protocol, in accordance with HIPAA mandate. These data originally appeared in the manuscript “Spontaneous Decoding of the Timing and Content of Human Object Perception from Cortical Surface Recordings Reveals Complementary Information in the Event-Related Potential and Broadband Spectral Change” published in PLoS Computational Biology in 2016 [Reference].
