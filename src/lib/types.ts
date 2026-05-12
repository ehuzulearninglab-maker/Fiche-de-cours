export interface PortfolioData {
  fullName: string;
  title: string;
  bio: string;
  skills: Skill[];
  education: Education[];
  experience: Experience[];
  projects: Project[];
  languages: string[];
  contact: ContactInfo;
  certifications: string[];
  theme: ThemeConfig;
}

export interface Skill {
  name: string;
  level: number;
  category: string;
}

export interface Education {
  degree: string;
  school: string;
  year: string;
  description: string;
}

export interface Experience {
  role: string;
  company: string;
  period: string;
  description: string;
  highlights: string[];
}

export interface Project {
  name: string;
  description: string;
  technologies: string[];
  link?: string;
}

export interface ContactInfo {
  email: string;
  phone: string;
  location: string;
  linkedin?: string;
  github?: string;
  website?: string;
}

export interface ThemeConfig {
  primary: string;
  secondary: string;
  accent: string;
  background: string;
  surface: string;
  text: string;
  textSecondary: string;
}
