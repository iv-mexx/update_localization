# update_localizations.py

A Python Script that helps dealing with localizations in Xcode. It keeps track of Items that are already translated and doesnt replace them like genstrings does but appends new items. 

Moreover it is possible to specify extensions of files that should be scanned and to specify ignore patterns for Files that should be ignored

# Swift

As long as you use only the default variant of `NSLocalizedString(value: comment:)` without additional parameters, this script works for swift as well. 

However, as soon as you need additional parameters, the `genstrings` tool break ([rdar://22817000](http://openradar.appspot.com/22817000)).

When you're working with swift, I'd suggest to manually edit your `.strings` files and use [R.swift](https://github.com/mac-cain13/R.swift) or [SwiftGen](https://github.com/AliSoftware/SwiftGen) to generate code for them.

## More Information

For more information read my original blog post at https://www.innovaptor.com/blog/2013/02/07/a-localization-workflow-that-works-well-in-practice/

For more information about the recommended workflow in swift, read my updated blog post at https://www.innovaptor.com/blog/2016/11/17/update-localization-workflow/
