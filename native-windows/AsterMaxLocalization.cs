using System;
using System.Globalization;
using System.Resources;

namespace PrePoMax
{
    internal static class AsterMaxLocalization
    {
        private static readonly ResourceManager Manager = new ResourceManager("PrePoMax.Localization.Strings", typeof(AsterMaxLocalization).Assembly);
        public static CultureInfo Culture { get; private set; } = CultureInfo.GetCultureInfo("es-CL");
        public static void SetCulture(string name) { Culture = CultureInfo.GetCultureInfo(name); }
        public static string T(string key, string fallback = null)
        {
            if (String.IsNullOrWhiteSpace(key)) return fallback ?? key;
            try { return Manager.GetString(key, Culture) ?? fallback ?? key; }
            catch (MissingManifestResourceException) { return fallback ?? key; }
        }
    }
}
