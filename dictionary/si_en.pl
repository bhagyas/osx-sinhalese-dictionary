#!/usr/bin/perl -w

# This script converts from en-si to si-en

# Copyright (C) 2008 by Buddhika Siddhisena (bud@sinhalenfoss.org)
# Released under the GNU General Public License
 
$INCLUDE_PHRASE = 0; # 0|1 to whether to include phrase a space or not
$file = './en-si.dict';

my(@sinword);

open(EN_SI, "$file") || die "Cant open $file!!!";
while ($line = <EN_SI>){
	# split by = to get english and sinhala parts
	my($en,$si) = split(/=/, $line);
	$en = strip($en);

	# split the sinhala part by | to get synonyms 
	my(@siw) = split(/\|/, $si);
	while ($si = shift @siw){ # go through the word list
		$si = strip($si);
		if($INCLUDE_PHRASE && $si=~/\s+/){
			# TODO Handle multiple words by removing stems
		}elsif(!($si=~/\s+/)){ # take single words only
			$sinword{$si}.="|$en";			
		}
	}

}

close(EN_SI);

foreach $si (keys %sinword){
	$sinword{$si}=~s/^\|//;
	print "$si\t$sinword{$si}\n";
}

sub strip{
	$word = shift @_;
	$word=~s/^\s//g;
	$word=~s/\s$//g;
 return $word;
}
