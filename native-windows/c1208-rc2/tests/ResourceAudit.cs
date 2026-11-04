using System;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;

class ResourceAudit
{
    static int Main(string[] args)
    {
        Assembly assembly = Assembly.LoadFile(Path.GetFullPath(args[0]));
        string[] names = assembly.GetManifestResourceNames();
        Array.Sort(names, StringComparer.Ordinal);
        foreach (string name in names)
        {
            using (Stream stream = assembly.GetManifestResourceStream(name))
            using (SHA256 sha = SHA256.Create())
            {
                long size = stream.Length;
                string hash = BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
                Console.WriteLine(name + "\t" + size + "\t" + hash);
            }
        }
        return 0;
    }
}
