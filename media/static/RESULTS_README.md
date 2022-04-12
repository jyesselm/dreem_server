## Summary of results.

This is a markdown file.

Results are broken into two main directories: "Mapping_Files" and "BitVector_Files."

The "Mapping_Files" directory summarizes the output of FastQC and Trim Galore!. 

## Mapping results

### FastQC output

The FastQC files will be HTML files in the format "fastq_filename_fastqc.html."

The HTML files give a breakdown of statistics for the sequencing quality found in the supplied fastq files. This includes:

- Basic Statistics
- Per base sequence quality
- Per tile sequence quality 
- Per sequence quality scores
- Per base sequence content 
- Per base N content
- Sequence Length Distribution 
- Sequence Duplication Levels
- Overrepresented sequences
- Adapter Content 

There is a lot of valuable data here. The "Per sequence quality scores" are of specific interest, which give a histogram of the read quality scores per sequence. A good run will be distributed towards higher Phred Scores, ideally all past 30. This estimates how confident the sequencer is of the assigned nucleotide value. 

Another check should be the "Sequence Length Distribution." How long were your reads supposed to be? If running on an Iseq, it should be 150 unless your RNA is smaller than this. Lots of reads at the wrong length may indicate a problem. 

### Trim Galore! output 

The Trim Galore output will be files that end in .fastq_trimming_report.txt. There should be one for each fastq file supplied. Trim Galore removes both reads below a quality cutoff set at 20 and trims off. The summary section documents how many reads it has processed, removed, and trimmed. 

```shell
=== Summary ===

Total reads processed:                 976,154
Reads with adapters:                   963,801 (98.7%)
Reads written (passing filters):       976,154 (100.0%)

Total basepairs processed:   135,685,406 bp
Quality-trimmed:                 264,137 bp (0.2%)
Total written (filtered):    102,339,372 bp (75.4%)
```
Good runs have high % Reads with adapters and a low number of quality-trimmed basepair.
 
## BitVector results

Files in the BitVector folder relate to the output related to the DMS reactivity per nucleotide.

Foreach reference sequence supplied there are 4 files generated: \_bitvectors.txt, \_popavg_reacts.csv, \_pop\_avg.html, \_pop\_avg.png.

For example, if the reference sequence is named 'test' and has a length of 100 nucleotides, then these will be the name of these files in BitVector_Files/

- test\_bitvectors.txt
- test\_1\_100\_pop\_avg.html
- test\_1\_100\_pop\_avg.png
- test\_1\_100\_popavg\_reacts.csv

The bitvectors.txt file contains a list of all the reads processed and what mutations they have. See the example below. 

```shell
@ref	test	AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA	DMS
@coordinates:	0,105:105
Query_name	Bit_vector	N_Mutations
FS10000899:120:BPN80007-2212:1:1101:4450:1000	00000000000000000000000000000000000000000000000000T000000000000000000000000000000000000000000000000000000	1
```
Each line contains a processed read and is tab-delimited. The first column is read name from the original fastq file. The second column contains the bitvectors. This string is the same length as the supplied reference sequence. A zero denotes no mutation at that position; a nucleotide letter represents a mutation; for example, a T means there was a mutation to a T at that position. Other possibilities are '?' which is ambiguous. The pair reads disagree, or the quality score is too low. '1' is a deletion, and. '' is missing data from the read. The last column is the number of mutations in the example; there is one mutation; thus, it reports 1.  

The pop_avg.html file is the same plot shown on the webserver. Plots mutation fraction, or the number of mutations observed at a position divided by the total number of reads for this position. Coloring is A: red, C: blue, G: orange, T: green. 

The pop_avg.png file is the PNG version of the .html file. 

The popavg_reacts.csv file contains data found in the plots in CSV format. The mismatches column considers only mismatch type mutations while mismatches_del considers both mismatches and deletions. 

Checking for good data quality

- ensure you have plenty of reads. Runs with less than 10,000 reads may have low signal to noise. 
- Check the range of reactivity. If all the reactivity values are below ~0.05 mutation fraction, this could be because there were not enough mutations.
- Check the average number of mutations per read. Ideally, one mutation is preferable. 



































