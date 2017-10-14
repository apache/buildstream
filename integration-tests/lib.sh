GREEN="\e[0;32m"
YELLOW="\e[0;33m"
RED="\e[0;31m"
END="\e[0m"

# patch_file_location
#
# Patch the location of a file in a file:// path.
#
# Args:
#    bst ($1) - The bst file to patch.
#    file ($2) - The file path to change to.
#
patch_file_location() {
	local bst="$1"
	local file="$2"

	sed -i "s|file://.*$|file://$file|" "$bst"
}

# check_permissions
#
# Compare the user execute permissions between two files.
#
# Args:
#    source ($1) - The first file
#    target ($2) - The second file
#
# Returns:
#    1 if the permissions mismatch
#
check_permissions () {
	local source="$1"
	local target="$2"
	local file_perm1
	local file_perm2

	# This only checks executable permissions since git will not
	# persist local permissions.
	file_perm1=$(stat -c '%A' "$source" | sed 's/...\(.\).\+/\1/')
	file_perm2=$(stat -c '%A' "$target" | sed 's/...\(.\).\+/\1/')

	if [ "$file_perm1" != "$file_perm2" ]
	then
		printf "Error: File permissions differ for files %s (%s) and %s (%s)" \
			   "$source" "$(stat -c '%A' "$source")" \
			   "$target" "$(stat -c '%A' "$target")\n"
		return 1
	fi
	return 0
}

# ensure_equal
#
# Recursively test for differences in content or permissions between
# the given directories.
#
# Args:
#    src ($1) - The first directory
#    target ($2) - The second directory
#
# Returns:
#    0 (bash true) if the files in the directories match, otherwise 1
#    if they mismatch
#
ensure_equal () (
	set +e

	local src="$1"
	local target="$2"

	local target_file
	local target_files
	local source_file

	# Check for file differences
	diff -r "$src" "$target"
	if [ $? -ne 0 ]
	then
		echo "Error: Unexpected or missing file in '$src'"
		return 1
	fi

	# Check for permission differences
	target_files=$(find "$target")
	for target_file in $target_files
	do
		source_file="$src${target_file#$target}"

		check_permissions "$source_file" "$target_file"
		if [ $? -ne 0 ]
		then
			echo "Error: File permissions differ for files '$source_file' and '$target_file'"
			return 1
		fi
	done

	return 0
)

# bst_with_flags
#
# Call bst with the flags defined by the main script.
#
bst_with_flags() {
    if [ ! -z "${BST_COVERAGE}" ]; then
	coverage run --parallel-mode \
		 --rcfile=${BST_COVERAGE} \
		 $(which bst) -c "${CONFIG_LOCATION}" ${BST_FLAGS:-} "$@"
    else
	bst -c "${CONFIG_LOCATION}" ${BST_FLAGS:-} "$@"
    fi
}

# report_results
#
# Args:
#    test_name ($1) - The name of the test
#    success ($2) - A bash truthy integer (0 is True, non 0 is False)
report_results() {
	test_name=$1
	success=$2

	if [ "$success" -eq 0 ]; then
		echo "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
		printf "%-34s ${GREEN}%9s${END}\n" "$test_name" "succeeded"
		echo "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
	else
		echo "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
		printf "%-34s ${RED}%9s${END}\n" "$test_name" "failed"
		echo "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
	fi
}

# compare_results
#
# Compare results to expected files, reporting success/failure for
# each test.
#
# Args:
#    test_name ($1) - The name of the test, for error reporting
#    result_dir ($2) - The directory containing result files
#    expected_dir ($3) - The directory containing expected files
#
# Returns:
#    0 if the files are equal, 1 otherwise.
#
compare_results() (
	set +e

	local test_name="$1"
	local result_dir="$2"
	local expected_dir="$3"

	ensure_equal "$result_dir/$test_name" "$expected_dir/$test_name"

	local success=$?
	report_results $test_name $success
	return $success
)

# comare_results_no_contents
#
# Compare results to expected files, ignoring the contents of the files,
# reporting success/failure for each test.
#
# Args:
#    test_name ($1) - The name of the test, for error reporting
#    result_dir ($2) - The directory containing result files
#    expected_dir ($3) - The directory containing expected files
#
# Returns:
#    1 if the dirs are equivalent, 0 otherwise.
compare_results_no_contents() (
	set +e

	local test_name="$1"
	local result_dir="$2"
	local expected_dir="$3"

	diff <(cd $result_dir/$test_name && find . | sort) <(cd $expected_dir/$test_name && find . | sort)
	local success=$?
	report_results $test_name $success
	return $success
)
