import traceback
try:
    import picasso.localize as loc
    print("SUCCESS: picasso.localize imported!")
except Exception as e:
    print("FAILED with Exception:", type(e), e)
    traceback.print_exc()
