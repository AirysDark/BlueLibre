package com.yourco.airpods

import android.content.Context
import android.content.SharedPreferences

object Prefs {
  private const val FILE = "airpods_prefs"
  private const val KEY_PREFER_COC = "prefer_coc"

  private fun prefs(ctx: Context): SharedPreferences =
    ctx.getSharedPreferences(FILE, Context.MODE_PRIVATE)

  fun setPreferCoc(ctx: Context, value: Boolean) {
    prefs(ctx).edit().putBoolean(KEY_PREFER_COC, value).apply()
  }

  fun getPreferCoc(ctx: Context): Boolean =
    prefs(ctx).getBoolean(KEY_PREFER_COC, /*default=*/true)
}
